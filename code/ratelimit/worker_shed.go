package ratelimit

// Chapter 06: the worker utilization load shedder - the last line of defence.
//
// No network call, local state only: a shedder that needs Redis is a shedder
// that fails when Redis is the problem. Shed gradually and restore gradually,
// or the system flaps.

import "sync/atomic"

type Class int

const (
	TestMode Class = iota
	Get
	Post
	Critical
)

type Shedder struct {
	inflight atomic.Int64
	capacity int64
}

func NewShedder(capacity int64) *Shedder { return &Shedder{capacity: capacity} }

func (s *Shedder) Enter() { s.inflight.Add(1) }
func (s *Shedder) Exit()  { s.inflight.Add(-1) }

func (s *Shedder) Utilization() float64 {
	return float64(s.inflight.Load()) / float64(s.capacity)
}

func (s *Shedder) Admit(c Class) bool {
	util := s.Utilization()
	switch {
	case util < 0.90:
		return true
	case util < 0.95:
		return c != TestMode
	case util < 0.98:
		return c == Post || c == Critical
	default:
		return c == Critical
	}
}
