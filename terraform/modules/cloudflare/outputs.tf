output "app_hostname" {
  description = "Public app hostname"
  value       = "app.${var.domain}"
}

output "api_hostname" {
  description = "Public API hostname"
  value       = "api.${var.domain}"
}

output "staging_hostname" {
  description = "Public staging hostname"
  value       = var.staging_origin != "" ? "staging.${var.domain}" : null
}

output "record_ids" {
  description = "Cloudflare DNS record IDs managed by this module"
  value = {
    app     = try(cloudflare_record.app[0].id, null)
    api     = try(cloudflare_record.api[0].id, null)
    staging = try(cloudflare_record.staging[0].id, null)
    root    = try(cloudflare_record.root[0].id, null)
    www     = try(cloudflare_record.www[0].id, null)
  }
}
