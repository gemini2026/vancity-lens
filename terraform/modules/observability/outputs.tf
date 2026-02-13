output "log_bucket_id" {
  description = "Cloud Logging bucket ID"
  value       = google_logging_project_bucket_config.application.id
}

output "log_archive_sink_name" {
  description = "Cloud Logging sink name for long-term archive"
  value       = google_logging_project_sink.archive.name
}

output "app_uptime_check_id" {
  description = "App uptime check resource id"
  value       = try(google_monitoring_uptime_check_config.app[0].uptime_check_id, null)
}

output "api_uptime_check_id" {
  description = "API uptime check resource id"
  value       = try(google_monitoring_uptime_check_config.api[0].uptime_check_id, null)
}
