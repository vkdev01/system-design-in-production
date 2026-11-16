package main

// Chapter 07: the gateway binary.
//
//   go run ./code/realtime/cmd/gateway --addr=:8080 --ring=cs-0,cs-1,cs-2

import (
	"flag"
	"log"
	"net/http"
	"os"
	"os/signal"
	"strings"
	"syscall"
	"time"

	"github.com/prometheus/client_golang/prometheus/promhttp"

	rt "github.com/vkdev01/system-design-in-production/code/realtime"
)

func main() {
	addr := flag.String("addr", ":8080", "listen address")
	ringAddrs := flag.String("ring", "cs-0,cs-1,cs-2", "channel server addresses")
	vnodes := flag.Int("vnodes", 160, "virtual nodes per channel server")
	flag.Parse()

	ring := rt.NewRing(*vnodes)
	for _, a := range strings.Split(*ringAddrs, ",") {
		if a = strings.TrimSpace(a); a != "" {
			ring.Add(a)
		}
	}
	ring.SetVersion(1)

	hub := rt.NewHub(ring, rt.NopChannelClient{})

	mux := http.NewServeMux()
	mux.HandleFunc("/ws", hub.ServeWS)
	mux.HandleFunc("/ready", func(w http.ResponseWriter, r *http.Request) {
		if ring.Version() == 0 {
			http.Error(w, "ring not loaded", http.StatusServiceUnavailable)
			return
		}
		w.WriteHeader(http.StatusOK)
	})
	mux.Handle("/metrics", promhttp.Handler())

	srv := &http.Server{Addr: *addr, Handler: mux}

	go func() {
		log.Printf("gateway listening on %s, ring version %d", *addr, ring.Version())
		if err := srv.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			log.Fatal(err)
		}
	}()

	// Drain on SIGTERM: tell clients to reconnect before the process dies.
	stop := make(chan os.Signal, 1)
	signal.Notify(stop, syscall.SIGTERM, syscall.SIGINT)
	<-stop
	log.Println("draining: sending reconnect frames")
	hub.Drain()
	time.Sleep(5 * time.Second)
}
