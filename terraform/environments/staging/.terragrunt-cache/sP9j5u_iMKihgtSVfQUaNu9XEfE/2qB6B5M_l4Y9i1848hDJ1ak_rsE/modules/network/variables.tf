variable "project_id" {
  description = "GCP Project ID"
  type        = string
}

variable "region" {
  description = "GCP region"
  type        = string
  default     = "us-west1"
}

variable "network_name" {
  description = "Name of the VPC network"
  type        = string
  default     = "vancity-lens-vpc"
}
