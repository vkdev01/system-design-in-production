package ratelimit

// Chapter 06: the request rate limiter, and the fail-open rule.
//
// A rate limiter exists to protect the API. It must never become a second way
// to take the API down, so every error path here allows the request.

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"strconv"
	"sync/atomic"
	"time"

	"github.com/prometheus/client_golang/prometheus"
	"github.com/redis/go-redis/v9"
)

var (
	degradedTotal = prometheus.NewCounter(prometheus.CounterOpts{
		Name: "ratelimit_degraded_total",
		Help: "Requests allowed because the limiter could not be consulted.",
	})
	limitedTotal = prometheus.NewCounter(prometheus.CounterOpts{
		Name: "ratelimit_rejected_total",
		Help: "Requests rejected by the rate limiter.",
	})
)

func init() { prometheus.MustRegister(degradedTotal, limitedTotal) }

type Decision struct {
	Allowed   bool
	Remaining int64
	Reason    string
}

type Limiter struct {
	rdb      redis.UniversalClient
	script   *redis.Script
	rate     float64
	capacity int
	timeout  time.Duration
	enabled  *atomic.Bool
	degraded prometheus.Counter
	limited  prometheus.Counter
}

func NewLimiter(rdb redis.UniversalClient, rate float64, capacity int,
	enabled *atomic.Bool) *Limiter {
	return &Limiter{
		rdb:      rdb,
		script:   redis.NewScript(tokenBucketLua),
		rate:     rate,
		capacity: capacity,
		timeout:  20 * time.Millisecond,
		enabled:  enabled,
		degraded: degradedTotal,
		limited:  limitedTotal,
	}
}

func (l *Limiter) Allow(ctx context.Context, user string, cost int) Decision {
	if l.enabled != nil && !l.enabled.Load() {
		return Decision{Allowed: true, Reason: "kill_switch"}
	}
	ctx, cancel := context.WithTimeout(ctx, l.timeout)
	defer cancel()

	// Hash tag keeps both keys in one cluster slot.
	keys := []string{"rl:{" + user + "}:tokens", "rl:{" + user + "}:ts"}
	res, err := l.script.Run(ctx, l.rdb, keys,
		l.rate, l.capacity, time.Now().Unix(), cost).Slice()
	if err != nil {
		l.degraded.Inc()
		return Decision{Allowed: true, Reason: "degraded"}
	}
	allowed := res[0].(int64) == 1
	remaining := res[1].(int64)
	if !allowed {
		l.limited.Inc()
	}
	return Decision{Allowed: allowed, Remaining: remaining, Reason: "bucket"}
}

// CostFor maps an endpoint to its weight in tokens. A batch endpoint that
// touches 100 rows should not cost the same as a single read.
func CostFor(r *http.Request) int {
	switch r.URL.Path {
	case "/v1/batch":
		return 20
	case "/v1/search":
		return 5
	default:
		return 1
	}
}

func (l *Limiter) Middleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		user := r.Header.Get("X-Account-Id")
		if user == "" {
			user = "anonymous"
		}
		d := l.Allow(r.Context(), user, CostFor(r))
		w.Header().Set("X-RateLimit-Limit", strconv.Itoa(l.capacity))
		w.Header().Set("X-RateLimit-Remaining", strconv.FormatInt(d.Remaining, 10))
		if !d.Allowed {
			w.Header().Set("Retry-After", "1")
			w.Header().Set("Content-Type", "application/problem+json")
			w.WriteHeader(http.StatusTooManyRequests)
			_ = json.NewEncoder(w).Encode(map[string]any{
				"type":   "rate_limit_error",
				"title":  "Too many requests",
				"detail": fmt.Sprintf("Limit is %.0f requests/second with bursts to %d. "+
					"Batch your requests or back off on 429.", l.rate, l.capacity),
			})
			return
		}
		next.ServeHTTP(w, r)
	})
}

const tokenBucketLua = `
local tokens_key = KEYS[1]
local timestamp_key = KEYS[2]
local rate = tonumber(ARGV[1])
local capacity = tonumber(ARGV[2])
local now = tonumber(ARGV[3])
local requested = tonumber(ARGV[4])
local fill_time = capacity / rate
local ttl = math.floor(fill_time * 2)
local last_tokens = tonumber(redis.call("get", tokens_key))
if last_tokens == nil then last_tokens = capacity end
local last_refreshed = tonumber(redis.call("get", timestamp_key))
if last_refreshed == nil then last_refreshed = 0 end
local delta = math.max(0, now - last_refreshed)
local filled_tokens = math.min(capacity, last_tokens + (delta * rate))
local allowed = filled_tokens >= requested
local new_tokens = filled_tokens
if allowed then new_tokens = filled_tokens - requested end
redis.call("setex", tokens_key, ttl, new_tokens)
redis.call("setex", timestamp_key, ttl, now)
return { allowed and 1 or 0, math.floor(new_tokens) }
`
