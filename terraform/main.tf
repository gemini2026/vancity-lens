# Enable required GCP APIs
resource "google_project_service" "required_apis" {
  for_each = toset([
    "compute.googleapis.com",
    "container.googleapis.com",
    "sqladmin.googleapis.com",
    "storage.googleapis.com",
    "artifactregistry.googleapis.com",
    "secretmanager.googleapis.com",
    "servicenetworking.googleapis.com",
    "logging.googleapis.com",
    "monitoring.googleapis.com",
    "run.googleapis.com",
    "cloudresourcemanager.googleapis.com",
  ])

  project = var.project_id
  service = each.value

  disable_on_destroy = true
}

locals {
  # Prefer an explicitly provided runtime URL; otherwise use Cloud SQL private IP.
  effective_database_url = trimspace(var.database_url) != "" ? var.database_url : format(
    "postgresql://%s@localhost:5432/%s",
    module.cloudsql.iam_database_user,
    module.cloudsql.database_name
  )

  effective_cloudflare_zone_id = trimspace(var.cloudflare_zone_id) != "" ? var.cloudflare_zone_id : (
    var.enable_cloudflare ? data.cloudflare_zone.primary[0].id : ""
  )
}

# Network Module
module "network" {
  source = "./modules/network"

  project_id   = var.project_id
  region       = var.region
  network_name = var.network_name

  depends_on = [google_project_service.required_apis]
}

# Cloud SQL Module
module "cloudsql" {
  source = "./modules/cloudsql"

  project_id                = var.project_id
  region                    = var.region
  network_id                = module.network.vpc_id
  db_password               = var.db_password
  gke_service_account_email = google_service_account.gke_sa.email

  depends_on = [
    google_project_service.required_apis,
    module.network
  ]
}

# GKE Module
module "gke" {
  source = "./modules/gke"

  project_id   = var.project_id
  region       = var.region
  network_id   = module.network.vpc_id
  subnet_id    = module.network.subnet_name
  cluster_name = var.cluster_name

  depends_on = [
    google_project_service.required_apis,
    module.network
  ]
}

resource "google_service_account" "gke_sa" {
  account_id   = "vancity-lens-gke-sa"
  display_name = "VanCity Lens GKE Service Account"
  project      = var.project_id
  description  = "Service account for VanCity Lens GKE cluster"

  depends_on = [google_project_service.required_apis]
}

# Grant necessary IAM roles to GKE service account
resource "google_project_iam_member" "gke_log_writer" {
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.gke_sa.email}"
}

resource "google_project_iam_member" "gke_metric_writer" {
  project = var.project_id
  role    = "roles/monitoring.metricWriter"
  member  = "serviceAccount:${google_service_account.gke_sa.email}"
}

resource "google_project_iam_member" "gke_monitoring_viewer" {
  project = var.project_id
  role    = "roles/monitoring.viewer"
  member  = "serviceAccount:${google_service_account.gke_sa.email}"
}

# Cloud SQL IAM roles for GKE service account (IAM auth via proxy)
resource "google_project_iam_member" "gke_cloudsql_client" {
  project = var.project_id
  role    = "roles/cloudsql.client"
  member  = "serviceAccount:${google_service_account.gke_sa.email}"
}

resource "google_project_iam_member" "gke_cloudsql_instance_user" {
  project = var.project_id
  role    = "roles/cloudsql.instanceUser"
  member  = "serviceAccount:${google_service_account.gke_sa.email}"
}

# Workload Identity binding: K8s SA → GCP SA
resource "google_service_account_iam_member" "gke_workload_identity" {
  service_account_id = google_service_account.gke_sa.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "serviceAccount:${var.project_id}.svc.id.goog[vancity-lens/vancity-lens-api]"
}

# Artifact Registry Module
module "registry" {
  source = "./modules/registry"

  project_id          = var.project_id
  region              = var.region
  gke_service_account = google_service_account.gke_sa.email

  depends_on = [
    google_project_service.required_apis,
    google_service_account.gke_sa
  ]
}

# Secrets Manager Module
module "secrets" {
  source = "./modules/secrets"

  project_id           = var.project_id
  anthropic_api_key    = var.anthropic_api_key
  cohere_api_key       = var.cohere_api_key
  database_url         = local.effective_database_url
  k2_api_key           = var.k2_api_key
  brave_search_api_key = var.brave_search_api_key
  admin_api_key        = var.admin_api_key
  jwt_secret           = var.jwt_secret
  rapidapi_key         = var.rapidapi_key
  db_password          = var.db_password
  environment_name     = var.environment_name
  gke_service_account  = google_service_account.gke_sa.email

  depends_on = [
    google_project_service.required_apis,
    google_service_account.gke_sa
  ]
}

# GCS buckets for source archive and long-term retention.
module "storage" {
  source = "./modules/storage"

  project_id                          = var.project_id
  region                              = var.region
  environment_name                    = var.environment_name
  archive_bucket_name                 = var.document_archive_bucket_name
  long_term_bucket_name               = var.document_long_term_bucket_name
  archive_transition_to_nearline_days = var.archive_transition_to_nearline_days
  archive_transition_to_coldline_days = var.archive_transition_to_coldline_days
  long_term_retention_days            = var.long_term_retention_days
  gke_service_account                 = google_service_account.gke_sa.email

  depends_on = [
    google_project_service.required_apis,
    google_service_account.gke_sa
  ]
}

# Logging and monitoring baseline.
module "observability" {
  source = "./modules/observability"

  project_id              = var.project_id
  environment_name        = var.environment_name
  log_archive_bucket_name = module.storage.long_term_bucket_name
  log_retention_days      = var.log_retention_days
  enable_uptime_checks    = var.enable_uptime_checks
  app_uptime_host         = var.monitoring_app_host
  api_uptime_host         = var.monitoring_api_host

  depends_on = [
    google_project_service.required_apis,
    module.storage
  ]
}

# GitHub Actions Self-Hosted Runner (GCE VM in VPC)
module "gh_runner" {
  source = "./modules/gh-runner"

  project_id                    = var.project_id
  region                        = var.region
  zone                          = "${var.region}-b"
  network_id                    = module.network.vpc_id
  subnet_id                     = module.network.subnet_id
  machine_type                  = var.runner_machine_type
  disk_size_gb                  = var.runner_disk_size_gb
  github_repo                   = var.github_repo
  github_runner_token_secret_id = var.github_runner_token_secret_id

  depends_on = [
    google_project_service.required_apis,
    module.network
  ]
}

# Cloudflare edge resources (optional; disabled by default until configured).
module "cloudflare" {
  count  = var.enable_cloudflare ? 1 : 0
  source = "./modules/cloudflare"

  zone_id             = local.effective_cloudflare_zone_id
  domain              = var.domain_name
  app_origin          = var.cloudflare_app_origin
  api_origin          = var.cloudflare_api_origin
  staging_origin      = var.cloudflare_staging_origin
  app_record_type     = var.cloudflare_app_record_type
  api_record_type     = var.cloudflare_api_record_type
  staging_record_type = var.cloudflare_staging_record_type

  enable_zone_settings = var.cloudflare_enable_zone_settings
}

# Cloud Run Service Account
resource "google_service_account" "cloudrun_sa" {
  count = var.enable_cloudrun ? 1 : 0

  account_id   = "vancity-lens-cloudrun-sa"
  display_name = "VanCity Lens Cloud Run Service Account"
  project      = var.project_id
  description  = "Service account for VanCity Lens Cloud Run API service"

  depends_on = [google_project_service.required_apis]
}

# Grant Cloud Run service account access to secrets
resource "google_secret_manager_secret_iam_member" "cloudrun_access_anthropic" {
  count = var.enable_cloudrun ? 1 : 0

  secret_id = module.secrets.anthropic_api_key_secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.cloudrun_sa[0].email}"

  depends_on = [module.secrets]
}

resource "google_secret_manager_secret_iam_member" "cloudrun_access_cohere" {
  count = var.enable_cloudrun ? 1 : 0

  secret_id = module.secrets.cohere_api_key_secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.cloudrun_sa[0].email}"

  depends_on = [module.secrets]
}

resource "google_secret_manager_secret_iam_member" "cloudrun_access_db_password" {
  count = var.enable_cloudrun ? 1 : 0

  secret_id = module.secrets.db_password_secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.cloudrun_sa[0].email}"

  depends_on = [module.secrets]
}

# Grant Cloud Run service account Cloud SQL client role
resource "google_project_iam_member" "cloudrun_sql_client" {
  count = var.enable_cloudrun ? 1 : 0

  project = var.project_id
  role    = "roles/cloudsql.client"
  member  = "serviceAccount:${google_service_account.cloudrun_sa[0].email}"
}

# Cloud Run Service for VanCity Lens API
resource "google_cloud_run_service" "api" {
  count = var.enable_cloudrun ? 1 : 0

  name     = "vancity-lens-api"
  location = var.region
  project  = var.project_id

  template {
    spec {
      service_account_name = google_service_account.cloudrun_sa[0].email

      containers {
        image = "${var.region}-docker.pkg.dev/${var.project_id}/${module.registry.repository_name}/api:latest"

        env {
          name  = "DATABASE_URL"
          value = "postgresql://${module.cloudsql.database_user}@/${module.cloudsql.database_name}?host=/cloudsql/${module.cloudsql.connection_name}"
        }

        env {
          name  = "ANTHROPIC_API_KEY"
          value = "sm://${var.project_id}/anthropic-api-key"
        }

        env {
          name  = "COHERE_API_KEY"
          value = "sm://${var.project_id}/cohere-api-key"
        }

        resources {
          limits = {
            cpu    = "2"
            memory = "1Gi"
          }
        }
      }

      timeout_seconds = 300
    }

    metadata {
      annotations = {
        "autoscaling.knative.dev/maxScale" = "5"
        "autoscaling.knative.dev/minScale" = "0"
      }
    }
  }

  traffic {
    percent         = 100
    latest_revision = true
  }

  depends_on = [
    google_project_service.required_apis,
    module.secrets,
    module.registry,
    module.cloudsql,
    google_service_account.cloudrun_sa,
    google_secret_manager_secret_iam_member.cloudrun_access_anthropic,
    google_secret_manager_secret_iam_member.cloudrun_access_cohere,
    google_secret_manager_secret_iam_member.cloudrun_access_db_password
  ]
}

# Cloud Run IAM - allow public access to the service
resource "google_cloud_run_service_iam_member" "cloudrun_invoker" {
  count = var.enable_cloudrun ? 1 : 0

  service  = google_cloud_run_service.api[0].name
  location = google_cloud_run_service.api[0].location
  role     = "roles/run.invoker"
  member   = "allUsers"

  depends_on = [google_cloud_run_service.api]
}
