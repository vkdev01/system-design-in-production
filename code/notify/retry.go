package notify

// Chapter 09: retries, terminal failures, and the DLQ.
//
// 4xx means the token is dead: delete it and never retry. 429/5xx mean back off
// with jitter, or the recovery becomes a second outage.

import (
	"context"
	"errors"
	"math/rand"
	"time"
)

type ErrorClass int

const (
	Success ErrorClass = iota
	Terminal
	Retryable
	CircuitOpen
)

var ErrExhausted = errors.New("retries exhausted")

func classify(err error) ErrorClass {
	if err == nil {
		return Success
	}
	var pe *ProviderError
	if errors.As(err, &pe) {
		switch {
		case pe.Status >= 400 && pe.Status < 500 && pe.Status != 429:
			return Terminal
		case pe.Status == 429 || pe.Status >= 500:
			return Retryable
		}
	}
	if errors.Is(err, ErrCircuitOpen) {
		return CircuitOpen
	}
	return Retryable
}

func (p *Pusher) sendWithRetry(ctx context.Context, r PushRequest) {
	backoff := 200 * time.Millisecond
	for attempt := 0; attempt < 4; attempt++ {
		err := p.client.Send(ctx, r)
		switch classify(err) {
		case Success:
			delivered.Inc()
			return
		case Terminal:
			p.dlq(r, err)
			return
		case CircuitOpen:
			p.requeue(r)
			return
		case Retryable:
			jitter := time.Duration(rand.Int63n(int64(backoff) / 2))
			select {
			case <-ctx.Done():
				return
			case <-time.After(backoff + jitter):
			}
			backoff *= 2
		}
	}
	p.dlq(r, ErrExhausted)
}

func (p *Pusher) dlq(r PushRequest, err error) { /* write to SQS DLQ + metric */ }
func (p *Pusher) requeue(r PushRequest)       { /* put it back without burning an attempt */ }
