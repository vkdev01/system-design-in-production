package main

// Chapter 03: the shard map and the routing decision.
//
// The application asks the same question it always asked; only the answer
// behind DBProxy changes. Everything about scaling without rewriting the app
// comes from this indirection.

import (
	"encoding/json"
	"fmt"
	"hash/fnv"
	"os"
	"sync"
)

type TableRule struct {
	ShardKey string `json:"shard_key"`
	Shards   int    `json:"shards"`
}

type ShardMap struct {
	mu      sync.RWMutex
	Version int                  `json:"version"`
	Tables  map[string]TableRule `json:"tables"`
	Pools   map[string]string    `json:"pools"` // shard name -> host:port
}

func LoadShardMap(path string) (*ShardMap, error) {
	b, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	m := &ShardMap{}
	if err := json.Unmarshal(b, m); err != nil {
		return nil, err
	}
	return m, nil
}

// Reload swaps the map atomically. A write carrying an old version is rejected
// rather than routed with stale knowledge: a stale map writes one workspace's
// rows to two different shards.
func (m *ShardMap) Reload(path string) error {
	next, err := LoadShardMap(path)
	if err != nil {
		return err
	}
	m.mu.Lock()
	defer m.mu.Unlock()
	if next.Version < m.Version {
		return fmt.Errorf("refusing to downgrade shard map %d -> %d", m.Version, next.Version)
	}
	m.Version = next.Version
	m.Tables = next.Tables
	m.Pools = next.Pools
	return nil
}

func (m *ShardMap) Route(table string, params map[string]any) (string, error) {
	m.mu.RLock()
	defer m.mu.RUnlock()

	rule, ok := m.Tables[table]
	if !ok {
		return "", fmt.Errorf("table %q is not sharded; route it explicitly", table)
	}
	v, ok := params[rule.ShardKey]
	if !ok {
		return "", fmt.Errorf("query on sharded table %q is missing routing key %q", table, rule.ShardKey)
	}
	return shardOf(v, rule.Shards), nil
}

func shardOf(v any, shards int) string {
	h := fnv.New64a()
	fmt.Fprintf(h, "%v", v)
	return fmt.Sprintf("shard-%02d", h.Sum64()%uint64(shards))
}
