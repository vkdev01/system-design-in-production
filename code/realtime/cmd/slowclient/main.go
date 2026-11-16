package main

// Chapter 07, drill: a client that connects and never reads.
// It must be disconnected and told to resync, and no other client may be
// affected. That is the whole point of the bounded outbound queue.

import (
	"log"
	"time"

	"github.com/gorilla/websocket"
)

func main() {
	conn, _, err := websocket.DefaultDialer.Dial("ws://localhost:8080/ws?client_id=slow-1", nil)
	if err != nil {
		log.Fatal(err)
	}
	defer conn.Close()
	// Deliberately never call ReadMessage.
	log.Println("connected and not reading; watch for a close frame and a metric increment")
	time.Sleep(10 * time.Minute)
}
