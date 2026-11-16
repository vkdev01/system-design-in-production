# Chapter 04/05: the money path. Multi-AZ is non-negotiable here.
terraform {
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 5.60" }
  }
}

resource "aws_db_instance" "payments" {
  identifier        = "payments-primary"
  engine            = "postgres"
  engine_version    = "16.4"
  instance_class    = "db.r6g.2xlarge"
  allocated_storage = 500
  max_allocated_storage = 4000
  storage_type      = "io2"
  iops              = 12000

  db_name  = "payments"
  username = "payments"
  password = var.db_password

  multi_az                = true
  deletion_protection     = true
  backup_retention_period = 35
  copy_tags_to_snapshot   = true
  performance_insights_enabled = true
  parameter_group_name    = aws_db_parameter_group.payments.name

  tags = { Tier = "money" }
}

resource "aws_db_parameter_group" "payments" {
  name   = "payments-primary"
  family = "postgres16"

  parameter { name = "max_connections", value = "400" }
  parameter { name = "statement_timeout", value = "5000" }
  parameter { name = "idle_in_transaction_session_timeout", value = "15000" }
  parameter { name = "synchronous_commit", value = "on" }   # never trade this on a money path
  parameter { name = "log_lock_waits", value = "1" }
}

variable "db_password" {
  type      = string
  sensitive = true
}
