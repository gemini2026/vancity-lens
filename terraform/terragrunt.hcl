# Root Terragrunt configuration for VanCity Lens

remote_state {
  backend = "gcs"
  config = {
    bucket         = "openclaw-antonmishel-03460-tf-state"
    prefix         = "terragrunt/${path_relative_to_include()}"
    project        = "openclaw-antonmishel-03460"
    location       = "us-west1"
    encryption_key = null  # Set to your encryption key in production
  }
  generate = {
    path      = "backend.tf"
    if_exists = "overwrite"
  }
}

# Inputs available to all environments
inputs = {
  labels = {
    managed_by  = "terragrunt"
    project     = "vancity-lens"
    environment = local.environment
  }
}
