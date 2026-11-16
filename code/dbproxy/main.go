package main

// Chapter 03: a minimal routing proxy.
//
// In production DBProxy speaks the Postgres wire protocol (jackc/pgproto3) so
// existing drivers work unchanged. This file keeps the decision logic and the
// metrics, and talks to the shards through pgx pools: the shape is the point.

import (
	"context"
	"errors"
	"fmt"
	"log"
	"net/http"
	"os"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promhttp"
)

var (
	unroutable = prometheus.NewCounterVec(prometheus.CounterOpts{
		Name: "dbproxy_unroutable_total",
		Help: "Queries that could not be routed to a shard. Alert on any increase.",
	}, []string{"table"})

	shardLatency = prometheus.NewHistogramVec(prometheus.HistogramOpts{
		Name:    "dbproxy_shard_duration_seconds",
		Buckets: prometheus.DefBuckets,
	}, []string{"shard"})
)

func init() {
	prometheus.MustRegister(unroutable, shardLatency)
}

type Proxy struct {
	map          *ShardMap
	pools        map[string]*pgxpool.Pool
	queryTimeout time.Duration
}

func NewProxy(m *ShardMap, timeout time.Duration) (*Proxy, error) {
	pools := make(map[string]*pgxpool.Pool, len(m.Pools))
	for name, dsn := range m.Pools {
		cfg, err := pgxpool.ParseConfig(dsn)
		if err != nil {
			return nil, fmt.Errorf("pool %s: %w", name, err)
		}
		cfg.MaxConns = 40 // per shard, per proxy replica
		pool, err := pgxpool.NewWithConfig(context.Background(), cfg)
		if err != nil {
			return nil, err
		}
		pools[name] = pool
	}
	return &Proxy{map: m, pools: pools, queryTimeout: timeout}, nil
}

type Query struct {
	Table  string
	SQL    string
	Params []any
	Args   map[string]any // routing params, extracted from the statement
}

func (p *Proxy) Exec(ctx context.Context, q Query) (any, error) {
	shard, err := p.map.Route(q.Table, q.Args)
	if err != nil {
		unroutable.WithLabelValues(q.Table).Inc()
		return nil, ErrUnroutable
	}
	pool, ok := p.pools[shard]
	if !ok {
		return nil, fmt.Errorf("no pool for %s", shard)
	}

	ctx, cancel := context.WithTimeout(ctx, p.queryTimeout) // 250ms
	defer cancel()

	start := time.Now()
	rows, err := pool.Query(ctx, q.SQL, q.Params...)
	shardLatency.WithLabelValues(shard).Observe(time.Since(start).Seconds())
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var out []map[string]any
	for rows.Next() {
		vals, err := rows.Values()
		if err != nil {
			return nil, err
		}
		rec := make(map[string]any, len(vals))
		for i, fd := range rows.FieldDescriptions() {
			rec[string(fd.Name)] = vals[i]
		}
		out = append(out, rec)
	}
	return out, rows.Err()
}

var ErrUnroutable = errors.New("query could not be routed: missing or unknown shard key")

func main() {
	path := os.Getenv("SHARD_MAP_PATH")
	if path == "" {
		path = "/etc/shardmap/map.json"
	}
	m, err := LoadShardMap(path)
	if err != nil {
		log.Fatalf("shard map: %v", err)
	}
	p, err := NewProxy(m, 250*time.Millisecond)
	if err != nil {
		log.Fatalf("proxy: %v", err)
	}

	http.Handle("/metrics", promhttp.Handler())
	http.HandleFunc("/ready", func(w http.ResponseWriter, r *http.Request) {
		// Ready only when every shard pool is warm.
		for name, pool := range p.pools {
			if err := pool.Ping(r.Context()); err != nil {
				http.Error(w, "shard "+name+" unreachable", http.StatusServiceUnavailable)
				return
			}
		}
		w.WriteHeader(http.StatusOK)
	})
	log.Printf("dbproxy ready: shard map version %d, %d pools", m.Version, len(p.pools))
	log.Fatal(http.ListenAndServe(":9090", nil))
}
