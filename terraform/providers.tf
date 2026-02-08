terraform {
  required_version = ">= 1.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
    google-beta = {
      source  = "hashicorp/google-beta"
      version = "~> 5.0"
    }
  }

  # GCS Backend for remote state storage
  # Configure via environment variables or -backend-config flag:
  # terraform init -backend-config="bucket=YOUR_BUCKET" \
  #   -backend-config="prefix=vancity-lens/terraform"
  backend "gcs" {
    # bucket - GCS bucket for state (pass via init flags or env var TF_BACKEND_BUCKET)
    # prefix - state file path (default: vancity-lens/terraform)
    # encryption_key - (optional) customer-managed encryption key for at-rest encryption
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

provider "google-beta" {
  project = var.project_id
  region  = var.region
}
