package main

// Chapter 01: the data service.
//
// One gRPC/HTTP endpoint per database query, no business logic, request
// coalescing, and consistent-hash routing so that all requests for a channel
// land on the same instance and can actually be coalesced.

import (
	"context"
	"encoding/json"
	"hash/fnv"
	"log"
	"net/http"
	"os"
	"strconv"
	"time"

	"github.com/gocql/gocql"
)

type Message struct {
	ChannelID int64     `json:"channel_id"`
	Bucket    int       `json:"bucket"`
	MessageID int64     `json:"message_id"`
	AuthorID  int64     `json:"author_id"`
	Content   string    `json:"content"`
	EditedAt  time.Time `json:"edited_at,omitempty"`
}

type Server struct {
	session   *gocql.Session
	coalescer *Coalescer
	shards    int
	timeout   time.Duration
	ring      []string
}

// bucketFor returns the static time window that a message ID falls into.
// 10-day windows: large enough to keep hot channels in few partitions, small
// enough that a single partition stays well under 100 MB.
func bucketFor(messageID int64) int {
	// Discord-style Snowflake: (ms since epoch << 22) | worker | sequence
	ms := (messageID >> 22) + 1420070400000
	return int(ms / (10 * 24 * 3600 * 1000))
}

func (s *Server) ownerFor(channelID int64) string {
	if len(s.ring) == 0 {
		return ""
	}
	h := fnv.New32a()
	h.Write([]byte(strconv.FormatInt(channelID, 10)))
	return s.ring[int(h.Sum32())%len(s.ring)]
}

func (s *Server) handleMessages(w http.ResponseWriter, r *http.Request) {
	q := r.URL.Query()
	channelID, err := strconv.ParseInt(q.Get("channel_id"), 10, 64)
	if err != nil {
		http.Error(w, "channel_id required", http.StatusBadRequest)
		return
	}
	after, _ := strconv.ParseInt(q.Get("after"), 10, 64)
	limit, _ := strconv.Atoi(q.Get("limit"))
	if limit <= 0 || limit > 200 {
		limit = 50
	}

	bucket := bucketFor(after)
	key := "chan:" + strconv.FormatInt(channelID, 10) + ":b:" + strconv.Itoa(bucket)

	ctx, cancel := context.WithTimeout(r.Context(), s.timeout)
	defer cancel()

	msgs, err := s.coalescer.Do(ctx, key, func(ctx context.Context) ([]Message, error) {
		// Straddle the bucket boundary: if the window is empty, read the one before.
		out, err := s.query(ctx, channelID, bucket, after, limit)
		if err != nil || len(out) == limit {
			return out, err
		}
		prev, err := s.query(ctx, channelID, bucket-1, after, limit-len(out))
		if err != nil {
			return out, nil
		}
		return append(out, prev...), nil
	})
	if err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}

	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(map[string]any{"messages": msgs, "bucket": bucket})
}

func (s *Server) query(ctx context.Context, channelID int64, bucket int, after int64, limit int) ([]Message, error) {
	var out []Message
	iter := s.session.Query(
		`SELECT channel_id, bucket, message_id, author_id, content, edited_at
		   FROM chat.messages
		  WHERE channel_id = ? AND bucket = ? AND message_id > ?
		  ORDER BY message_id DESC LIMIT ?`,
		channelID, bucket, after, limit,
	).WithContext(ctx).Iter()

	var m Message
	for iter.Scan(&m.ChannelID, &m.Bucket, &m.MessageID, &m.AuthorID, &m.Content, &m.EditedAt) {
		out = append(out, m)
	}
	return out, iter.Close()
}

func (s *Server) handleReady(w http.ResponseWriter, _ *http.Request) {
	// Readiness depends only on local state: the ring and the session.
	if s.session == nil {
		http.Error(w, "no session", http.StatusServiceUnavailable)
		return
	}
	w.WriteHeader(http.StatusOK)
	_, _ = w.Write([]byte("ok"))
}

func main() {
	cluster := gocql.NewCluster(env("SCYLLA_HOSTS", "127.0.0.1"))
	cluster.Keyspace = "chat"
	cluster.Consistency = gocql.LocalQuorum
	cluster.Timeout = 500 * time.Millisecond

	session, err := cluster.CreateSession()
	if err != nil {
		log.Fatalf("scylla: %v", err)
	}
	defer session.Close()

	s := &Server{
		session:   session,
		coalescer: NewCoalescer(),
		timeout:   250 * time.Millisecond,
		ring:      []string{"ds-0", "ds-1", "ds-2", "ds-3", "ds-4", "ds-5"},
	}

	mux := http.NewServeMux()
	mux.HandleFunc("/messages", s.handleMessages)
	mux.HandleFunc("/ready", s.handleReady)
	mux.HandleFunc("/metrics", func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "text/plain")
		_, _ = w.Write([]byte("# HELP coalescer_inflight_queries in-flight coalesced queries\n"))
		_, _ = w.Write([]byte("# TYPE coalescer_inflight_queries gauge\n"))
		_, _ = w.Write([]byte("coalescer_inflight_queries " + strconv.Itoa(s.coalescer.InFlight()) + "\n"))
	})

	log.Println("message-dataservice listening on :8080")
	log.Fatal(http.ListenAndServe(":8080", mux))
}

func env(k, def string) string {
	if v := os.Getenv(k); v != "" {
		return v
	}
	return def
}
