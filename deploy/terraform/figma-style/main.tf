# Chapter 03: vertical partitions, one RDS per table group, then shards later.
terraform {
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 5.60" }
  }
}

locals {
  partitions = {
    files    = { instance = "db.r6g.8xlarge", storage = 4000, iops = 32000 }
    orgs     = { instance = "db.r6g.4xlarge", storage = 2000, iops = 16000 }
    comments = { instance = "db.r6g.4xlarge", storage = 2000, iops = 16000 }
    billing  = { instance = "db.r6g.xlarge", storage = 500, iops = 8000 }
  }
}

resource "aws_db_instance" "partition" {
  for_each = local.partitions

  identifier        = "figma-${each.key}"
  engine            = "postgres"
  engine_version    = "16.4"
  instance_class    = each.value.instance
  allocated_storage = each.value.storage
  storage_type      = "io2"
  iops              = each.value.iops

  db_name  = replace(each.key, "-", "_")
  username = "figma"
  password = var.db_password

  multi_az                = true
  performance_insights_enabled          = true
  performance_insights_retention_period = 465
  parameter_group_name    = aws_db_parameter_group.partition[each.key].name
  deletion_protection     = true
}

resource "aws_db_parameter_group" "partition" {
  for_each = local.partitions
  name     = "figma-${each.key}"
  family   = "postgres16"

  parameter { name = "autovacuum_vacuum_scale_factor", value = "0.02" }
  parameter { name = "idle_in_transaction_session_timeout", value = "30000" }
  parameter { name = "statement_timeout", value = "15000" }
}

variable "db_password" {
  type      = string
  sensitive = true
}
