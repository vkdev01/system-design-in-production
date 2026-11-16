package main

// Chapter 09, drill 1: inject a burst and watch the shed policy work.
//
//   go run ./code/notify/cmd/burst --rate 17000 --seconds 60
//
// Expect: the buffer fills, shedding starts, and transactional latency stays
// flat. If transactional latency moves, the priority classes are not wired.

import (
	"context"
	"flag"
	"fmt"
	"log"
	"time"

	"github.com/vkdev01/system-design-in-production/code/notify"
)

func main() {
	rate := flag.Int("rate", 17000, "pushes per second")
	seconds := flag.Int("seconds", 60, "burst duration")
	buffer := flag.Int("buffer", 8000, "collector buffer size")
	conns := flag.Int("conns", 4, "provider connections")
	perConn := flag.Int("provider-inflight", 100, "in-flight limit per connection")
	flag.Parse()

	collector := notify.NewCollector(*buffer)
	pusher := notify.NewPusher(collector, notify.NewStubProvider(100), *conns, *perConn)

	ctx, cancel := context.WithTimeout(context.Background(), time.Duration(*seconds)*time.Second)
	defer cancel()
	go pusher.Run(ctx)

	ticker := time.NewTicker(time.Second)
	defer ticker.Stop()

	var sent, accepted int
	deadline := time.Now().Add(time.Duration(*seconds) * time.Second)

	for time.Now().Before(deadline) {
		<-ticker.C
		// One second's worth of traffic, pushed as fast as we can enqueue it.
		for i := 0; i < *rate; i++ {
			sent++
			if collector.Accept(notify.PushRequest{
				UserID:   fmt.Sprintf("u%d", sent%1_000_000),
				DeviceID: "d1",
				Provider: "fcm",
				Priority: "social",
				Collapse: "thread",
			}) {
				accepted++
			}
		}
		log.Printf("sent=%d accepted=%d buffered=%d", sent, accepted, collector.Depth())
	}
	log.Printf("done: sent=%d accepted=%d shed=%d", sent, accepted, sent-accepted)
}
