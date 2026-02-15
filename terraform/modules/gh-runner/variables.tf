variable "project_id" {
  description = "GCP Project ID"
  type        = string
}

variable "region" {
  description = "GCP region"
  type        = string
}

variable "zone" {
  description = "GCP zone for the runner instance"
  type        = string
}

variable "network_id" {
  description = "VPC network self-link"
  type        = string
}

variable "subnet_id" {
  description = "Subnet self-link for the runner instance"
  type        = string
}

variable "machine_type" {
  description = "GCE machine type for the runner"
  type        = string
  default     = "e2-medium"
}

variable "disk_size_gb" {
  description = "Boot disk size in GB"
  type        = number
  default     = 50
}

variable "github_repo" {
  description = "GitHub repository in owner/repo format"
  type        = string
}

variable "runner_name" {
  description = "Name for the GitHub Actions runner"
  type        = string
  default     = "vancity-lens-gce"
}

variable "runner_labels" {
  description = "Comma-separated extra labels for the runner"
  type        = string
  default     = ""
}

variable "github_runner_token_secret_id" {
  description = "Secret Manager secret ID containing the GitHub PAT for runner registration"
  type        = string
}
