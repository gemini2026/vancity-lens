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
  description = "VPC Network ID or name"
  type        = string
}

variable "subnet_id" {
  description = "Subnet ID or name"
  type        = string
}

variable "cluster_name" {
  description = "Name of the GKE cluster"
  type        = string
  default     = "vancity-lens-gke"
}
