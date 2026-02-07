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

variable "db_password" {
  description = "Database password"
  type        = string
  sensitive   = true
}

variable "gke_service_account" {
  description = "GKE service account email for IAM permissions"
  type        = string
  default     = ""
}
