package notify

// Chapter 09: dedupe and collapse.
//
// A burst is usually a few events fanned out to millions of devices, so most of
// the work is duplicate suppression. "3 new messages" beats three pushes.
//
// Note the fail-open decision: a duplicate push is annoying, a missing
// password-reset push is a support ticket. Decide per feature.

import (
	"context"
	"fmt"
	"time"

	"github.com/redis/go-redis/v9"
)

type Deduper struct {
	rdb redis.UniversalClient
	ttl time.Duration
}

func NewDeduper(rdb redis.UniversalClient) *Deduper {
	return &Deduper{rdb: rdb, ttl: 10 * time.Minute}
}

func CollapseKey(n PushRequest, window time.Duration) string {
	slot := time.Now().Unix() / int64(window.Seconds())
	return fmt.Sprintf("n:%s:%s:%d", n.UserID, n.Collapse, slot)
}

func (d *Deduper) Allow(ctx context.Context, n PushRequest) (bool, error) {
	ok, err := d.rdb.SetNX(ctx, CollapseKey(n, 5*time.Minute), n.DeviceID, d.ttl).Result()
	if err != nil {
		return true, err // fail open
	}
	return ok, nil
}
