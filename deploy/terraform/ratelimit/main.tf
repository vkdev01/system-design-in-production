# Chapter 06: ElastiCache Redis in cluster mode for rate-limit state.
terraform {
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 5.60" }
  }
}

resource "aws_elasticache_replication_group" "rl" {
  replication_group_id = "ratelimit"
  description          = "rate limit counters"

  engine         = "redis"
  engine_version = "7.1"
  node_type      = "cache.r7g.large"
  port           = 6379

  num_node_groups         = 3      # shard by key; a single shard is a hot-key SPOF
  replicas_per_node_group = 1
  automatic_failover_enabled = true
  multi_az_enabled           = true

  at_rest_encryption_enabled = true
  transit_encryption_enabled = true

  parameter_group_name = aws_elasticache_parameter_group.rl.name
  apply_immediately    = false

  tags = { Chapter = "06" }
}

resource "aws_elasticache_parameter_group" "rl" {
  name   = "ratelimit-redis7"
  family = "redis7"

  # Every limiter key has a TTL, so volatile-lru can never evict a live counter.
  parameter {
    name  = "maxmemory-policy"
    value = "volatile-lru"
  }
}
