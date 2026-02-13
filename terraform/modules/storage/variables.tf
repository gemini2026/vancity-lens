variable "project_id" {
  description = "GCP project ID"
  type        = string
}

variable "region" {
  description = "Bucket region"
  type        = string
  default     = "us-west1"
}

variable "environment_name" {
  description = "Environment name (dev/staging/prod)"
  type        = string
  default     = "dev"
}

variable "archive_bucket_name" {
  description = "Override for the document archive bucket name"
  type        = string
  default     = ""
}

variable "long_term_bucket_name" {
  description = "Override for the long-term retention bucket name"
  type        = string
  default     = ""
}

variable "archive_transition_to_nearline_days" {
  description = "Days before archive bucket objects transition to NEARLINE"
  type        = number
  default     = 30
}

variable "archive_transition_to_coldline_days" {
  description = "Days before archive bucket objects transition to COLDLINE"
  type        = number
  default     = 180
}

variable "long_term_retention_days" {
  description = "Object lock retention for long-term bucket"
  type        = number
  default     = 365
}
