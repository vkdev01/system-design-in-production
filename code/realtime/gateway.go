package realtime

// Chapter 07: the gateway - sockets, subscriptions, bounded outbound queues.
//
// The `default:` branch in deliver() is the most important code in this file:
// one client on a bad mobile connection must not stall delivery to 50,000
// others.

import (
	"encoding/json"
	"log"
	"net/http"
	"sync"
	"time"

	"github.com/gorilla/websocket"
)

type Client struct {
	id       string
	userID   string
	conn     *websocket.Conn
	out      chan []byte
	channels map[string]struct{}
	closeOnce sync.Once
}

var upgrader = websocket.Upgrader{
	ReadBufferSize:  4096,
	WriteBufferSize: 4096,
	CheckOrigin:     func(r *http.Request) bool { return true },
}

type Hub struct {
	mu       sync.RWMutex
	clients  map[string]*Client
	byChan   map[string]map[string]struct{} // channel -> client ids
	ring     *Ring
	cs       ChannelClient
}

func NewHub(ring *Ring, cs ChannelClient) *Hub {
	return &Hub{
		clients: make(map[string]*Client),
		byChan:  make(map[string]map[string]struct{}),
		ring:    ring,
		cs:      cs,
	}
}

func (h *Hub) ServeWS(w http.ResponseWriter, r *http.Request) {
	conn, err := upgrader.Upgrade(w, r, nil)
	if err != nil {
		return
	}
	c := &Client{
		id:       r.URL.Query().Get("client_id"),
		userID:   r.Header.Get("X-User-Id"),
		conn:     conn,
		out:      make(chan []byte, 256), // bounded: the slow-consumer policy
		channels: map[string]struct{}{},
	}

	h.mu.Lock()
	h.clients[c.id] = c
	h.mu.Unlock()

	go c.writePump()
	go h.readPump(c)
}

func (c *Client) writePump() {
	ticker := time.NewTicker(30 * time.Second)
	defer func() {
		ticker.Stop()
		_ = c.conn.Close()
	}()
	for {
		select {
		case msg, ok := <-c.out:
			_ = c.conn.SetWriteDeadline(time.Now().Add(10 * time.Second))
			if !ok {
				_ = c.conn.WriteMessage(websocket.CloseMessage, nil)
				return
			}
			if err := c.conn.WriteMessage(websocket.TextMessage, msg); err != nil {
				return
			}
		case <-ticker.C:
			_ = c.conn.SetWriteDeadline(time.Now().Add(10 * time.Second))
			if err := c.conn.WriteMessage(websocket.PingMessage, nil); err != nil {
				return
			}
		}
	}
}

func (h *Hub) readPump(c *Client) {
	defer h.remove(c)
	for {
		_, data, err := c.conn.ReadMessage()
		if err != nil {
			return
		}
		var env Envelope
		if err := json.Unmarshal(data, &env); err != nil {
			continue
		}
		switch env.Type {
		case "subscribe":
			h.subscribe(c, env.ChannelID)
		case "typing": // transient: gateway -> channel server, never persisted
			h.cs.Transient(h.ring.Owner(env.ChannelID), env)
		case "message":
			h.cs.Publish(h.ring.Owner(env.ChannelID), h.ring.Version(), env)
		}
	}
}

func (h *Hub) subscribe(c *Client, channelID string) {
	h.mu.Lock()
	if h.byChan[channelID] == nil {
		h.byChan[channelID] = map[string]struct{}{}
	}
	h.byChan[channelID][c.id] = struct{}{}
	c.channels[channelID] = struct{}{}
	h.mu.Unlock()

	// Tell the owning channel server that this gateway cares about the channel.
	h.cs.Subscribe(h.ring.Owner(channelID), channelID, c.id)
}

// deliver is called by the channel-server subscription stream.
func (h *Hub) deliver(channelID string, payload []byte) {
	h.mu.RLock()
	ids := h.byChan[channelID]
	targets := make([]*Client, 0, len(ids))
	for id := range ids {
		if c, ok := h.clients[id]; ok {
			targets = append(targets, c)
		}
	}
	h.mu.RUnlock()

	for _, c := range targets {
		select {
		case c.out <- payload:
		default:
			slowConsumerDrops.Inc()
			log.Printf("client %s is a slow consumer on %s; closing for resync", c.id, channelID)
			c.closeOnce.Do(func() { close(c.out) })
			h.remove(c)
		}
	}
}

func (h *Hub) remove(c *Client) {
	h.mu.Lock()
	delete(h.clients, c.id)
	for ch := range c.channels {
		delete(h.byChan[ch], c.id)
	}
	h.mu.Unlock()
}
