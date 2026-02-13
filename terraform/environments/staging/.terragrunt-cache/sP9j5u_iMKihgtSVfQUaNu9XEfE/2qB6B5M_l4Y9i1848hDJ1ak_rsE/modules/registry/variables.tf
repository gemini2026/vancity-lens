variable "project_id" {
  description = "GCP Project ID"
  type        = string
}

variable "region" {
  description = "GCP region"
  type        = string
  default     = "us-west1"
}

variable "gke_service_account" {
  description = "GKE service account email for IAM permissions"
  type        = string
  default     = ""
}
