locals {
  log_bucket_id = "vancity-lens-${var.environment_name}-logs"
}

resource "google_logging_project_bucket_config" "application" {
  project        = var.project_id
  location       = "global"
  bucket_id      = local.log_bucket_id
  retention_days = var.log_retention_days

  description = "Application log bucket for VanCity Lens (${var.environment_name})"
}

resource "google_logging_project_sink" "archive" {
  project                = var.project_id
  name                   = "vancity-lens-${var.environment_name}-log-archive"
  destination            = "storage.googleapis.com/${var.log_archive_bucket_name}"
  unique_writer_identity = true

  # Route runtime logs to long-term GCS storage.
  filter = "resource.type=(\"k8s_container\" OR \"k8s_pod\" OR \"k8s_node\")"
}

resource "google_storage_bucket_iam_member" "archive_writer" {
  bucket = var.log_archive_bucket_name
  role   = "roles/storage.objectCreator"
  member = google_logging_project_sink.archive.writer_identity
}

resource "google_monitoring_uptime_check_config" "app" {
  count        = var.enable_uptime_checks && var.app_uptime_host != "" ? 1 : 0
  project      = var.project_id
  display_name = "vancity-lens-${var.environment_name}-app"
  timeout      = "10s"
  period       = "60s"

  monitored_resource {
    type = "uptime_url"
    labels = {
      project_id = var.project_id
      host       = var.app_uptime_host
    }
  }

  http_check {
    path         = "/"
    port         = 443
    use_ssl      = true
    validate_ssl = true
  }
}

resource "google_monitoring_uptime_check_config" "api" {
  count        = var.enable_uptime_checks && var.api_uptime_host != "" ? 1 : 0
  project      = var.project_id
  display_name = "vancity-lens-${var.environment_name}-api"
  timeout      = "10s"
  period       = "60s"

  monitored_resource {
    type = "uptime_url"
    labels = {
      project_id = var.project_id
      host       = var.api_uptime_host
    }
  }

  http_check {
    path         = "/health"
    port         = 443
    use_ssl      = true
    validate_ssl = true
  }
}
