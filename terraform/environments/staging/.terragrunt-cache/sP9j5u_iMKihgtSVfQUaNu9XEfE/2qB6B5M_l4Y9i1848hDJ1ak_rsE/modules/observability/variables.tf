variable "project_id" {
  description = "GCP project ID"
  type        = string
}

variable "environment_name" {
  description = "Environment name"
  type        = string
  default     = "dev"
}

variable "log_archive_bucket_name" {
  description = "GCS bucket used for long-term Cloud Logging export"
  type        = string
}

variable "log_retention_days" {
  description = "Retention period for primary logging bucket"
  type        = number
  default     = 30
}

variable "enable_uptime_checks" {
  description = "Enable uptime checks for app/api hosts"
  type        = bool
  default     = false
}

variable "app_uptime_host" {
  description = "App hostname for uptime checks"
  type        = string
  default     = ""
}

variable "api_uptime_host" {
  description = "API hostname for uptime checks"
  type        = string
  default     = ""
}
