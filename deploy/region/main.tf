# Chapter 19: latency routing with health checks, plus Global Accelerator for the
# failover that DNS alone cannot do inside a minute.
terraform {
  required_version = ">= 1.6"
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 5.60" }
  }
}

variable "zone_id" {}
variable "alb_dns" { type = map(string) }
variable "alb_zone_id" { type = string }

locals {
  regions = ["ap-south-1", "ap-southeast-1"]
}

resource "aws_route53_health_check" "region" {
  for_each          = toset(local.regions)
  fqdn              = "api.${each.key}.example.com"
  port              = 443
  type              = "HTTPS"
  resource_path     = "/healthz"      # must touch only local state
  failure_threshold = 3
  request_interval  = 10
}

resource "aws_route53_record" "api" {
  for_each       = toset(local.regions)
  zone_id        = var.zone_id
  name           = "api.example.com"
  type           = "A"
  set_identifier = each.key
  latency_routing_policy {
    region = each.key
  }
  health_check_id = aws_route53_health_check.region[each.key].id
  alias {
    name                   = var.alb_dns[each.key]
    zone_id                = var.alb_zone_id
    evaluate_target_health = true
  }
}

resource "aws_globalaccelerator_accelerator" "api" {
  name            = "api-global"
  ip_address_type = "IPV4"
  enabled         = true
  attributes {
    flow_logs_enabled = true
  }
}
