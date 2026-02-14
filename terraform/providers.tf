terraform {
  required_version = ">= 1.0"

  # GCS backend is configured dynamically by Terragrunt (see root.hcl).
  # For standalone use without Terragrunt, uncomment and configure:
  # backend "gcs" {
  #   bucket  = "openclaw-antonmishel-03460-tf-state"
  #   prefix  = "terraform/state"
  #   project = "openclaw-antonmishel-03460"
  # }

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
    google-beta = {
      source  = "hashicorp/google-beta"
      version = "~> 5.0"
    }
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = "~> 4.0"
    }
  }

}

locals {
  cloudflare_provider_api_token = var.enable_cloudflare ? var.cloudflare_api_token : "0000000000000000000000000000000000000000"
}

provider "google" {
  project = var.project_id
  region  = var.region
}

provider "google-beta" {
  project = var.project_id
  region  = var.region
}

provider "cloudflare" {
  api_token = local.cloudflare_provider_api_token
}
