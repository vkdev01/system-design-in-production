package main

// Chapter 01: request coalescing.
//
// If 5,000 users ask for the same row at the same instant, exactly one query
// should reach the database and all 5,000 should subscribe to its result.
// This is the mechanism that made Discord's data services worth writing.

import (
	"context"
	"sync"
)

type call struct {
	wg  sync.WaitGroup
	val []Message
	err error
}

// Coalescer collapses concurrent identical requests into one execution.
// Entries are deleted as soon as they finish, so this is not a cache: it only
// deduplicates requests that are genuinely in flight at the same time.
type Coalescer struct {
	mu    sync.Mutex
	calls map[string]*call
}

func NewCoalescer() *Coalescer {
	return &Coalescer{calls: make(map[string]*call)}
}

func (c *Coalescer) Do(ctx context.Context, key string, fn func(context.Context) ([]Message, error)) ([]Message, error) {
	c.mu.Lock()
	if existing, ok := c.calls[key]; ok {
		c.mu.Unlock()
		existing.wg.Wait()
		return existing.val, existing.err
	}
	n := &call{}
	n.wg.Add(1)
	c.calls[key] = n
	c.mu.Unlock()

	n.val, n.err = fn(ctx)
	n.wg.Done()

	c.mu.Lock()
	delete(c.calls, key)
	c.mu.Unlock()

	return n.val, n.err
}

// InFlight is exported for the HPA metric: scale on coalesced queries in flight,
// not on CPU, because this service is latency-bound.
func (c *Coalescer) InFlight() int {
	c.mu.Lock()
	defer c.mu.Unlock()
	return len(c.calls)
}
