package realtime

// Chapter 07: the consistent hash ring.
//
// Virtual nodes smooth the distribution (16 million channels on 12 pods without
// vnodes is very uneven). The ring is control-plane data: it is loaded from
// config and watched, never computed per request.

import (
	"fmt"
	"sort"
	"sync"

	"github.com/cespare/xxhash/v2"
)

type Ring struct {
	mu        sync.RWMutex
	version   int
	vnodes    []uint64
	owner     map[uint64]string
	perNode   int
}

func NewRing(perNode int) *Ring {
	return &Ring{owner: make(map[uint64]string), perNode: perNode}
}

func (r *Ring) Add(addr string) {
	r.mu.Lock()
	defer r.mu.Unlock()
	for i := 0; i < r.perNode; i++ {
		h := xxhash.Sum64String(fmt.Sprintf("%s#%d", addr, i))
		r.owner[h] = addr
		r.vnodes = append(r.vnodes, h)
	}
	sort.Slice(r.vnodes, func(i, j int) bool { return r.vnodes[i] < r.vnodes[j] })
}

func (r *Ring) SetVersion(v int) {
	r.mu.Lock()
	defer r.mu.Unlock()
	r.version = v
}

func (r *Ring) Version() int {
	r.mu.RLock()
	defer r.mu.RUnlock()
	return r.version
}

// Owner returns the channel server that owns this channel.
func (r *Ring) Owner(channelID string) string {
	r.mu.RLock()
	defer r.mu.RUnlock()
	if len(r.vnodes) == 0 {
		return ""
	}
	h := xxhash.Sum64String(channelID)
	i := sort.Search(len(r.vnodes), func(i int) bool { return r.vnodes[i] >= h })
	if i == len(r.vnodes) {
		i = 0
	}
	return r.owner[r.vnodes[i]]
}

// Owners returns the primary and one successor, for replication. A ring member
// with no replica means a node loss is a visible gap, not a blip.
func (r *Ring) Owners(channelID string, n int) []string {
	r.mu.RLock()
	defer r.mu.RUnlock()
	if len(r.vnodes) == 0 {
		return nil
	}
	h := xxhash.Sum64String(channelID)
	start := sort.Search(len(r.vnodes), func(i int) bool { return r.vnodes[i] >= h })
	out := make([]string, 0, n)
	seen := map[string]bool{}
	for i := 0; i < len(r.vnodes) && len(out) < n; i++ {
		addr := r.owner[r.vnodes[(start+i)%len(r.vnodes)]]
		if !seen[addr] {
			seen[addr] = true
			out = append(out, addr)
		}
	}
	return out
}
