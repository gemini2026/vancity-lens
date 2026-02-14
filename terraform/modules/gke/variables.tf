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

variable "master_authorized_cidr_blocks" {
  description = "CIDR blocks allowed to access the GKE master API. Must not be 0.0.0.0/0 in production."
  type = list(object({
    cidr_block   = string
    display_name = string
  }))
  default = [
    {
      cidr_block   = "10.0.0.0/8"
      display_name = "Private networks"
    }
  ]
}
