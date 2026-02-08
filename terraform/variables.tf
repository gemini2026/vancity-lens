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
  description = "Password for Cloud SQL database user"
  type        = string
  sensitive   = true
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

variable "cloudrun_container_image" {
  description = "Cloud Run container image URL"
  type        = string
  default     = ""
}

variable "cloudrun_min_instances" {
  description = "Minimum number of Cloud Run instances"
  type        = number
  default     = 0
}

variable "cloudrun_max_instances" {
  description = "Maximum number of Cloud Run instances"
  type        = number
  default     = 5
}

variable "environment_name" {
  description = "Environment name (dev, staging, prod)"
  type        = string
  default     = "dev"
}
