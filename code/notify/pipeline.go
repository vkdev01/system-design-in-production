package notify

// Chapter 09: a bounded queue between an unbounded producer and a rate-limited
// consumer.
//
// Backpressure is the mechanism: the pusher asks for work, so the provider's
// in-flight limit propagates all the way back to the producer. Shedding is the
// policy: when the buffer is full, we drop and count it, because dropping a
// notification is an acceptable outcome and an outage is not.

import (
	"context"
	"time"

	"github.com/prometheus/client_golang/prometheus"
)

var (
	shed      = prometheus.NewCounter(prometheus.CounterOpts{Name: "notify_shed_total", Help: "Requests shed because the buffer was full."})
	delivered = prometheus.NewCounter(prometheus.CounterOpts{Name: "notify_delivered_total", Help: "Notifications delivered."})
)

func init() { prometheus.MustRegister(shed, delivered) }

type PushRequest struct {
	UserID   string
	DeviceID string
	Provider string // fcm | apns | webpush
	Title    string
	Body     string
	Priority string // transactional | social
	Collapse string
}

type Collector struct {
	buf chan PushRequest
}

func NewCollector(bufferSize int) *Collector {
	return &Collector{buf: make(chan PushRequest, bufferSize)}
}

// Accept never blocks. A full buffer means shed, immediately and visibly.
func (c *Collector) Accept(req PushRequest) bool {
	select {
	case c.buf <- req:
		return true
	default:
		shed.Inc()
		return false
	}
}

func (c *Collector) Depth() int { return len(c.buf) }

type ProviderClient interface {
	Send(ctx context.Context, req PushRequest) error
}

type Pusher struct {
	in      *Collector
	client  ProviderClient
	conns   int
	perConn int // the provider's hard in-flight limit, e.g. 100
}

func NewPusher(in *Collector, client ProviderClient, conns, perConn int) *Pusher {
	return &Pusher{in: in, client: client, conns: conns, perConn: perConn}
}

// Run asks for work only when it has capacity.
func (p *Pusher) Run(ctx context.Context) error {
	sem := make(chan struct{}, p.conns*p.perConn)
	for {
		select {
		case <-ctx.Done():
			return ctx.Err()
		case sem <- struct{}{}:
		}
		select {
		case req := <-p.in.buf:
			go func(r PushRequest) {
				defer func() { <-sem }()
				p.sendWithRetry(ctx, r)
			}(req)
		default:
			<-sem
			time.Sleep(5 * time.Millisecond)
		}
	}
}
