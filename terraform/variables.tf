variable "project_id" {
  description = "GCP Project ID"
  type        = string
}

variable "region" {
  description = "GCP region (us-west1 is closest to Vancouver)"
  type        = string
  default     = "us-west1"
}

variable "network_name" {
  description = "Name of the VPC network"
  type        = string
  default     = "vancity-lens-vpc"
}

variable "cluster_name" {
  description = "Name of the GKE cluster"
  type        = string
  default     = "vancity-lens-gke"
}

variable "db_password" {
  description = "Password for Cloud SQL database user (optional — empty uses IAM auth)"
  type        = string
  sensitive   = true
  default     = ""
}

variable "anthropic_api_key" {
  description = "Anthropic API Key for Claude integration"
  type        = string
  sensitive   = true
}

variable "cohere_api_key" {
  description = "Cohere API Key for embeddings"
  type        = string
  sensitive   = true
}

variable "database_url" {
  description = "Database URL consumed by API/worker workloads"
  type        = string
  sensitive   = true
  default     = ""
}

variable "k2_api_key" {
  description = "K2 API key"
  type        = string
  sensitive   = true
  default     = ""
}

variable "brave_search_api_key" {
  description = "Brave Search API key"
  type        = string
  sensitive   = true
  default     = ""
}

variable "admin_api_key" {
  description = "Admin API key for protected admin endpoints"
  type        = string
  sensitive   = true
  default     = ""
}

variable "jwt_secret" {
  description = "JWT secret for user authentication tokens"
  type        = string
  sensitive   = true
  default     = ""
}

variable "rapidapi_key" {
  description = "RapidAPI key for Realtor.ca scraper"
  type        = string
  sensitive   = true
  default     = ""
}

variable "environment_name" {
  description = "Environment name (dev, staging, prod)"
  type        = string
  default     = "dev"
}

variable "enable_cloudrun" {
  description = "Enable optional Cloud Run resources (disabled for GKE-first rollout)"
  type        = bool
  default     = false
}

variable "document_archive_bucket_name" {
  description = "Optional override for document archive bucket name"
  type        = string
  default     = ""
}

variable "document_long_term_bucket_name" {
  description = "Optional override for document long-term bucket name"
  type        = string
  default     = ""
}

variable "archive_transition_to_nearline_days" {
  description = "Days before archive objects transition to NEARLINE"
  type        = number
  default     = 30
}

variable "archive_transition_to_coldline_days" {
  description = "Days before archive objects transition to COLDLINE"
  type        = number
  default     = 180
}

variable "long_term_retention_days" {
  description = "Retention lock (days) for long-term documents bucket"
  type        = number
  default     = 365
}

variable "log_retention_days" {
  description = "Retention period for the primary Cloud Logging bucket"
  type        = number
  default     = 30
}

variable "enable_uptime_checks" {
  description = "Enable Monitoring uptime checks for app/api hosts"
  type        = bool
  default     = false
}

variable "monitoring_app_host" {
  description = "Hostname for app uptime checks"
  type        = string
  default     = ""
}

variable "monitoring_api_host" {
  description = "Hostname for api uptime checks"
  type        = string
  default     = ""
}

variable "enable_cloudflare" {
  description = "Enable Cloudflare resources management in Terraform"
  type        = bool
  default     = false
}

variable "cloudflare_api_token" {
  description = "Cloudflare API token with DNS/WAF permissions for the target zone"
  type        = string
  sensitive   = true
  default     = ""
}

variable "cloudflare_zone_id" {
  description = "Cloudflare Zone ID for vancitylense.com"
  type        = string
  default     = ""
}

variable "domain_name" {
  description = "Primary root domain for production"
  type        = string
  default     = "vancitylense.com"
}

variable "cloudflare_app_origin" {
  description = "DNS target for app subdomain (LB hostname or IP)"
  type        = string
  default     = ""
}

variable "cloudflare_api_origin" {
  description = "DNS target for api subdomain (LB hostname or IP)"
  type        = string
  default     = ""
}

variable "cloudflare_staging_origin" {
  description = "DNS target for staging subdomain (optional)"
  type        = string
  default     = ""
}

variable "cloudflare_app_record_type" {
  description = "Record type for app target (A/CNAME)"
  type        = string
  default     = "A"
}

variable "cloudflare_api_record_type" {
  description = "Record type for api target (A/CNAME)"
  type        = string
  default     = "A"
}

variable "cloudflare_staging_record_type" {
  description = "Record type for staging target (A/CNAME)"
  type        = string
  default     = "A"
}

variable "cloudflare_enable_zone_settings" {
  description = "Whether Terraform should manage Cloudflare zone settings overrides"
  type        = bool
  default     = false
}
