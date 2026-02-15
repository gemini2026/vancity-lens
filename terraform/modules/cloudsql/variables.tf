variable "project_id" {
  description = "GCP Project ID"
  type        = string
}

variable "region" {
  description = "GCP region"
  type        = string
  default     = "us-west1"
}

variable "network_id" {
  description = "VPC Network ID for private service connection"
  type        = string
}

variable "db_password" {
  description = "Password for the vancity database user (optional — empty disables password user)"
  type        = string
  sensitive   = true
  default     = ""
}

variable "gke_service_account_email" {
  description = "GKE service account email for Cloud SQL IAM authentication"
  type        = string
}
