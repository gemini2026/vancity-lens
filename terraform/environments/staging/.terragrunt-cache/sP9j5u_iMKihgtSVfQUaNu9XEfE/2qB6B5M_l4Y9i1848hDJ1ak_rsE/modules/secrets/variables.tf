variable "project_id" {
  description = "GCP Project ID"
  type        = string
}

variable "anthropic_api_key" {
  description = "Anthropic API Key"
  type        = string
  sensitive   = true
}

variable "cohere_api_key" {
  description = "Cohere API Key"
  type        = string
  sensitive   = true
}

variable "database_url" {
  description = "Database URL used by application workloads"
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

variable "db_password" {
  description = "Database password"
  type        = string
  sensitive   = true
  validation {
    condition     = trimspace(var.db_password) != ""
    error_message = "db_password must be non-empty."
  }
}

variable "environment_name" {
  description = "Environment label value"
  type        = string
  default     = "dev"
}

variable "gke_service_account" {
  description = "GKE service account email for IAM permissions"
  type        = string
  default     = ""
}
