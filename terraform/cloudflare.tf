data "cloudflare_zone" "primary" {
  count = var.enable_cloudflare && trimspace(var.cloudflare_zone_id) == "" ? 1 : 0
  name  = var.domain_name
}
