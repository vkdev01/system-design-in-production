package realtime

// Chapter 07: subscription setup, region affinity and reconnect behaviour.
//
// Reconnect rules learned across the industry:
//   - jitter the delay, or a regional blip becomes a self-inflicted DDoS
//   - resume from last_seen_message_id instead of re-syncing everything
//   - drain before death: send a control frame, let clients move

import (
	"context"
	"math/rand"
	"sync"
	"time"
)

func (h *Hub) OnConnect(ctx context.Context, c *Client, lastSeen int64) error {
	chans, err := h.userChannels(ctx, c.userID)
	if err != nil {
		return err
	}

	sem := make(chan struct{}, 32)
	var wg sync.WaitGroup
	for _, ch := range chans {
		wg.Add(1)
		sem <- struct{}{}
		go func(ch string) {
			defer wg.Done()
			defer func() { <-sem }()
			owner := h.ring.Owner(ch)
			if err := h.cs.SubscribeWithResume(owner, ch, c.id, lastSeen); err != nil {
				h.retrySubscribe(ctx, owner, ch, c.id, lastSeen)
			}
		}(ch)
	}
	wg.Wait()
	return nil
}

func (h *Hub) retrySubscribe(ctx context.Context, owner, ch, clientID string, lastSeen int64) {
	for attempt := 0; attempt < 5; attempt++ {
		// Full jitter: base * (1 + rand). Without this, every client retries at once.
		backoff := time.Duration(200*(1<<attempt)) * time.Millisecond
		jitter := time.Duration(rand.Int63n(int64(backoff)))
		select {
		case <-ctx.Done():
			return
		case <-time.After(backoff + jitter):
		}
		// The ring may have changed while we were waiting: re-resolve the owner.
		if err := h.cs.SubscribeWithResume(h.ring.Owner(ch), ch, clientID, lastSeen); err == nil {
			return
		}
	}
}

// Drain tells every connected client to reconnect elsewhere before the pod dies.
func (h *Hub) Drain() {
	h.mu.RLock()
	defer h.mu.RUnlock()
	msg := []byte(`{"type":"control","action":"reconnect","reason":"draining"}`)
	for _, c := range h.clients {
		select {
		case c.out <- msg:
		default:
		}
	}
}

func (h *Hub) userChannels(ctx context.Context, userID string) ([]string, error) {
	// In production this is a call to the Webapp backend; Slack's gateway does
	// exactly this on connect and sends the first message with the channel list.
	return []string{"general", "eng-backend"}, nil
}
