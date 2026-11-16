# Chapter 08: PostGIS + h3-pg for the index of record, Redis for the hot path.
terraform {
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 5.60" }
  }
}

resource "aws_db_instance" "geo" {
  identifier        = "geo-postgis"
  engine            = "postgres"
  engine_version    = "16.4"
  instance_class    = "db.r6g.4xlarge"
  allocated_storage = 1000
  storage_type      = "io2"
  iops              = 16000

  db_name  = "geo"
  username = "geo"
  password = var.db_password

  multi_az             = true
  parameter_group_name = aws_db_parameter_group.geo.name
  performance_insights_enabled = true
}

resource "aws_db_parameter_group" "geo" {
  name   = "geo-postgis"
  family = "postgres16"

  parameter { name = "shared_preload_libraries", value = "pg_stat_statements" }
  parameter { name = "max_connections", value = "600" }
  parameter { name = "statement_timeout", value = "3000" }
}

resource "aws_elasticache_replication_group" "geo" {
  replication_group_id = "geo-positions"
  description          = "latest driver positions, sharded by city"
  engine               = "redis"
  engine_version       = "7.1"
  node_type            = "cache.r7g.xlarge"
  num_node_groups         = 3
  replicas_per_node_group = 1
  automatic_failover_enabled = true
  multi_az_enabled           = true
  at_rest_encryption_enabled = true
  transit_encryption_enabled = true
}

variable "db_password" {
  type      = string
  sensitive = true
}
