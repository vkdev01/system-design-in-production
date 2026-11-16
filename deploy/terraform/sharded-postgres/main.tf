# Chapter 02: the sharded Postgres fleet.
# 96 physical databases, 480 logical shards (5 per database), PgBouncer in front.
terraform {
  required_version = ">= 1.6"
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 5.60" }
  }
}

variable "environment" { default = "prod" }
variable "databases" { default = 96 }

resource "aws_db_instance" "shard" {
  count = var.databases

  identifier        = "notion-db-${format("%02d", count.index)}"
  engine            = "postgres"
  engine_version    = "16.4"
  instance_class    = "db.r6g.4xlarge"
  allocated_storage = 2000
  max_allocated_storage = 10000
  storage_type      = "io2"
  iops              = 16000
  storage_throughput = 1000

  db_name  = "notion"
  username = "notion"
  password = var.db_password

  multi_az                = true
  backup_retention_period = 14
  backup_window           = "18:00-19:00"   # 23:30-00:30 IST
  maintenance_window      = "sun:19:00-sun:20:00"
  auto_minor_version_upgrade = false

  performance_insights_enabled          = true
  performance_insights_retention_period = 465
  deletion_protection                   = true

  parameter_group_name = aws_db_parameter_group.shard.name

  tags = {
    Environment = var.environment
    ShardMap    = "v2"
  }
}

resource "aws_db_parameter_group" "shard" {
  name   = "notion-shard-${var.environment}"
  family = "postgres16"

  parameter { name = "max_connections", value = "800" }
  parameter { name = "autovacuum_vacuum_scale_factor", value = "0.02" }
  parameter { name = "autovacuum_naptime", value = "15" }
  parameter { name = "idle_in_transaction_session_timeout", value = "30000" }
  parameter { name = "statement_timeout", value = "15000" }
  parameter { name = "track_io_timing", value = "1" }
  parameter { name = "log_min_duration_statement", value = "500" }
}

variable "db_password" {
  type      = string
  sensitive = true
}

output "endpoints" {
  value = aws_db_instance.shard[*].endpoint
}
