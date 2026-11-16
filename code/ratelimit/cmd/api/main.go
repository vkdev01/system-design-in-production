package main

// Chapter 06: a tiny API that limits itself, so the drills have something to
// hit.   go run ./code/ratelimit/cmd/api --rate=100 --burst=500
//
// Kill the Redis container while this runs: every request must still succeed,
// and ratelimit_degraded_total must climb. That is the fail-open rule.

import (
	"context"
	"flag"
	"log"
	"net/http"
	"os"
	"sync/atomic"
	"time"

	"github.com/prometheus/client_golang/prometheus/promhttp"
	"github.com/redis/go-redis/v9"

	rt "github.com/vkdev01/system-design-in-production/code/ratelimit"
)

func main() {
	addr := flag.String("addr", ":8080", "listen address")
	rate := flag.Float64("rate", 100, "tokens per second")
	burst := flag.Int("burst", 500, "bucket capacity")
	redisAddr := flag.String("redis", os.Getenv("REDIS_ADDR"), "redis address")
	flag.Parse()
	if *redisAddr == "" {
		*redisAddr = "localhost:6379"
	}

	rdb := redis.NewClient(&redis.Options{Addr: *redisAddr})
	if err := rdb.Ping(context.Background()).Err(); err != nil {
		log.Printf("redis unreachable at %s: %v (limiter will fail open)", *redisAddr, err)
	}

	enabled := &atomic.Bool{}
	enabled.Store(true)

	limiter := rt.NewLimiter(rdb, *rate, *burst, enabled)
	shedder := rt.NewShedder(int64(*burst))

	mux := http.NewServeMux()
	mux.Handle("/metrics", promhttp.Handler())
	mux.HandleFunc("/ready", func(w http.ResponseWriter, r *http.Request) {
		// Deliberately independent of Redis.
		w.WriteHeader(http.StatusOK)
	})
	mux.HandleFunc("/admin/ratelimit", func(w http.ResponseWriter, r *http.Request) {
		on := r.URL.Query().Get("enabled") != "false"
		enabled.Store(on)
		log.Printf("kill switch: enabled=%v", on)
		w.WriteHeader(http.StatusNoContent)
	})
	mux.Handle("/v1/ping", limiter.Middleware(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if !shedder.Admit(rt.Get) {
			w.WriteHeader(http.StatusServiceUnavailable)
			return
		}
		shedder.Enter()
		defer shedder.Exit()
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte("pong"))
	})))

	srv := &http.Server{Addr: *addr, Handler: mux, ReadHeaderTimeout: 5 * time.Second}
	log.Printf("api on %s: rate=%.0f/s burst=%d", *addr, *rate, *burst)
	log.Fatal(srv.ListenAndServe())
}
