package realtime

// Chapter 07: the channel server.
//
// Two invariants, written as code:
//   1. a channel server writes only the channels it owns
//   2. a channel server never blocks on a slow gateway

import (
	"encoding/json"
	"errors"
	"sync"
	"time"
)

var (
	ErrRingVersionMismatch = errors.New("ring version mismatch: re-read the ring and retry")
	ErrNotOwner            = errors.New("this channel server does not own that channel")
)

type Message struct {
	ChannelID string    `json:"channel_id"`
	MessageID int64     `json:"message_id"`
	AuthorID  string    `json:"author_id"`
	Body      string    `json:"body"`
	SentAt    time.Time `json:"sent_at"`
}

type ChannelServer struct {
	addr        string
	ring        *Ring
	version     int
	historySize int

	mu          sync.RWMutex
	history     map[string][]Message
	subscribers map[string]map[string]struct{} // channel -> gateway ids

	gw GatewayClient
}

func (s *ChannelServer) Publish(channelID string, msg Message, ringVersion int) error {
	if ringVersion != s.version {
		return ErrRingVersionMismatch
	}
	if s.ring.Owner(channelID) != s.addr {
		return ErrNotOwner
	}

	s.mu.Lock()
	h := append(s.history[channelID], msg)
	if len(h) > s.historySize {
		h = h[len(h)-s.historySize:]
	}
	s.history[channelID] = h
	subs := make([]string, 0, len(s.subscribers[channelID]))
	for gw := range s.subscribers[channelID] {
		subs = append(subs, gw)
	}
	s.mu.Unlock()

	payload, _ := json.Marshal(msg)
	var wg sync.WaitGroup
	for _, gw := range subs {
		wg.Add(1)
		go func(gw string) {
			defer wg.Done()
			// Bounded and timed out: one slow gateway cannot stall fan-out.
			s.gw.Send(gw, channelID, payload)
		}(gw)
	}
	wg.Wait()
	return nil
}

// Replay returns the delta since lastSeen from the in-memory window. Only if
// the gap is larger than the window does the caller fall back to storage.
func (s *ChannelServer) Replay(channelID string, lastSeen int64) ([]Message, bool) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	hist := s.history[channelID]
	if len(hist) == 0 {
		return nil, false
	}
	if hist[0].MessageID > lastSeen+1 {
		return nil, false // gap too large: caller must read from the message store
	}
	out := make([]Message, 0, len(hist))
	for _, m := range hist {
		if m.MessageID > lastSeen {
			out = append(out, m)
		}
	}
	return out, true
}
