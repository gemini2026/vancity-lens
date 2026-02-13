locals {
  sanitized_project               = lower(replace(var.project_id, "_", "-"))
  effective_archive_bucket_name   = var.archive_bucket_name != "" ? var.archive_bucket_name : "${local.sanitized_project}-${var.environment_name}-docs-archive"
  effective_long_term_bucket_name = var.long_term_bucket_name != "" ? var.long_term_bucket_name : "${local.sanitized_project}-${var.environment_name}-docs-longterm"
  long_term_retention_seconds     = var.long_term_retention_days * 24 * 60 * 60
}

resource "google_storage_bucket" "archive" {
  name                        = local.effective_archive_bucket_name
  project                     = var.project_id
  location                    = var.region
  storage_class               = "STANDARD"
  force_destroy               = false
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"

  versioning {
    enabled = true
  }

  lifecycle_rule {
    condition {
      age = var.archive_transition_to_nearline_days
    }
    action {
      type          = "SetStorageClass"
      storage_class = "NEARLINE"
    }
  }

  lifecycle_rule {
    condition {
      age = var.archive_transition_to_coldline_days
    }
    action {
      type          = "SetStorageClass"
      storage_class = "COLDLINE"
    }
  }

  labels = {
    app         = "vancity-lens"
    environment = var.environment_name
    data_class  = "archive"
  }
}

resource "google_storage_bucket" "long_term" {
  name                        = local.effective_long_term_bucket_name
  project                     = var.project_id
  location                    = var.region
  storage_class               = "STANDARD"
  force_destroy               = false
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"

  versioning {
    enabled = true
  }

  retention_policy {
    retention_period = local.long_term_retention_seconds
  }

  lifecycle_rule {
    condition {
      age = 30
    }
    action {
      type          = "SetStorageClass"
      storage_class = "ARCHIVE"
    }
  }

  labels = {
    app         = "vancity-lens"
    environment = var.environment_name
    data_class  = "long_term"
  }
}
