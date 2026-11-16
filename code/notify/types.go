package notify

import (
	"context"
	"errors"
	"fmt"
)

var ErrCircuitOpen = errors.New("provider circuit open")

type ProviderError struct {
	Status int
	Body   string
}

func (e *ProviderError) Error() string {
	return fmt.Sprintf("provider %d: %s", e.Status, e.Body)
}

// StubProvider is a local stand-in that enforces the same in-flight limit the
// real provider does. Drill 2: set --provider-inflight above 100 and watch 429s.
type StubProvider struct {
	inflight chan struct{}
}

func NewStubProvider(limit int) *StubProvider {
	return &StubProvider{inflight: make(chan struct{}, limit)}
}

func (s *StubProvider) Send(ctx context.Context, req PushRequest) error {
	select {
	case s.inflight <- struct{}{}:
		defer func() { <-s.inflight }()
	default:
		return &ProviderError{Status: 429, Body: "too many in-flight requests"}
	}
	select {
	case <-ctx.Done():
		return ctx.Err()
	case <-timeAfter(50 * 1e6): // 50ms
		return nil
	}
}
