terraform {
  required_providers {
    cloudflare = {
      source = "cloudflare/cloudflare"
    }
  }
}

locals {
  app_hostname     = "app.${var.domain}"
  api_hostname     = "api.${var.domain}"
  staging_hostname = "staging.${var.domain}"
}

# Primary frontend hostname
resource "cloudflare_record" "app" {
  count = var.app_origin != "" ? 1 : 0

  zone_id = var.zone_id
  name    = "app"
  type    = var.app_record_type
  value   = var.app_origin
  ttl     = 1
  proxied = var.app_proxied
}

# Public API hostname
resource "cloudflare_record" "api" {
  count = var.api_origin != "" ? 1 : 0

  zone_id = var.zone_id
  name    = "api"
  type    = var.api_record_type
  value   = var.api_origin
  ttl     = 1
  proxied = var.api_proxied
}

# Optional staging hostname
resource "cloudflare_record" "staging" {
  count   = var.staging_origin != "" ? 1 : 0
  zone_id = var.zone_id
  name    = "staging"
  type    = var.staging_record_type
  value   = var.staging_origin
  ttl     = 1
  proxied = var.staging_proxied
}

# Root and www aliases (frontend entrypoints)
resource "cloudflare_record" "root" {
  count = var.app_origin != "" ? 1 : 0

  zone_id = var.zone_id
  name    = "@"
  type    = "CNAME"
  value   = local.app_hostname
  ttl     = 1
  proxied = true
}

resource "cloudflare_record" "www" {
  count = var.app_origin != "" ? 1 : 0

  zone_id = var.zone_id
  name    = "www"
  type    = "CNAME"
  value   = local.app_hostname
  ttl     = 1
  proxied = true
}

# Baseline SSL and transport policy for the zone.
resource "cloudflare_zone_settings_override" "baseline" {
  count   = var.enable_zone_settings ? 1 : 0
  zone_id = var.zone_id

  settings {
    ssl                      = var.ssl_mode
    always_use_https         = var.always_use_https ? "on" : "off"
    automatic_https_rewrites = "on"
    tls_1_3                  = "on"
    min_tls_version          = "1.2"
  }
}
