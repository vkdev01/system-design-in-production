package realtime

// Chapter 07: the seams. In production these are gRPC clients generated from
// the channel-server and gateway protos; here they are interfaces so the
// wiring is visible.

import (
	"github.com/prometheus/client_golang/prometheus"
)

var slowConsumerDrops = prometheus.NewCounter(prometheus.CounterOpts{
	Name: "gateway_slow_consumer_drops_total",
	Help: "Clients closed because their outbound queue filled up.",
})

func init() { prometheus.MustRegister(slowConsumerDrops) }

type Envelope struct {
	Type      string `json:"type"` // subscribe | message | typing | control
	ChannelID string `json:"channel_id,omitempty"`
	Body      string `json:"body,omitempty"`
	MessageID int64  `json:"message_id,omitempty"`
}

type ChannelClient interface {
	Subscribe(csAddr, channelID, clientID string) error
	SubscribeWithResume(csAddr, channelID, clientID string, lastSeen int64) error
	Publish(csAddr string, ringVersion int, env Envelope) error
	Transient(csAddr string, env Envelope) error
}

type GatewayClient interface {
	// Send must be bounded: return an error rather than blocking fan-out.
	Send(gwAddr, channelID string, payload []byte) error
}

type NopChannelClient struct{}

func (NopChannelClient) Subscribe(csAddr, channelID, clientID string) error {
	return nil
}
func (NopChannelClient) SubscribeWithResume(csAddr, channelID, clientID string, lastSeen int64) error {
	return nil
}
func (NopChannelClient) Publish(csAddr string, ringVersion int, env Envelope) error { return nil }
func (NopChannelClient) Transient(csAddr string, env Envelope) error               { return nil }
