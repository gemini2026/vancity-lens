# Enable required GCP APIs
resource "google_project_service" "required_apis" {
  for_each = toset([
    "compute.googleapis.com",
    "container.googleapis.com",
    "sqladmin.googleapis.com",
    "artifactregistry.googleapis.com",
    "secretmanager.googleapis.com",
    "servicenetworking.googleapis.com",
    "cloudlogging.googleapis.com",
    "monitoring.googleapis.com",
    "run.googleapis.com",
    "cloudresourcemanager.googleapis.com",
  ])

  project = var.project_id
  service = each.value

  disable_on_destroy = true
}

# Network Module
module "network" {
  source = "./modules/network"

  project_id  = var.project_id
  region      = var.region
  network_name = var.network_name

  depends_on = [google_project_service.required_apis]
}

# Cloud SQL Module
module "cloudsql" {
  source = "./modules/cloudsql"

  project_id = var.project_id
  region     = var.region
  network_id = module.network.vpc_id
  db_password = var.db_password

  depends_on = [
    google_project_service.required_apis,
    module.network
  ]
}

# GKE Module
module "gke" {
  source = "./modules/gke"

  project_id = var.project_id
  region     = var.region
  network_id = module.network.vpc_id
  subnet_id  = module.network.subnet_name
  cluster_name = var.cluster_name

  depends_on = [
    google_project_service.required_apis,
    module.network
  ]
}

# Get GKE default service account
data "google_client_config" "default" {}

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

  project_id          = var.project_id
  anthropic_api_key   = var.anthropic_api_key
  cohere_api_key      = var.cohere_api_key
  db_password         = var.db_password
  gke_service_account = google_service_account.gke_sa.email

  depends_on = [
    google_project_service.required_apis,
    google_service_account.gke_sa
  ]
}

# Cloud Run Service Account
resource "google_service_account" "cloudrun_sa" {
  account_id   = "vancity-lens-cloudrun-sa"
  display_name = "VanCity Lens Cloud Run Service Account"
  project      = var.project_id
  description  = "Service account for VanCity Lens Cloud Run API service"

  depends_on = [google_project_service.required_apis]
}

# Grant Cloud Run service account access to secrets
resource "google_secret_manager_secret_iam_member" "cloudrun_access_anthropic" {
  secret_id = module.secrets.anthropic_api_key_secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.cloudrun_sa.email}"

  depends_on = [module.secrets]
}

resource "google_secret_manager_secret_iam_member" "cloudrun_access_cohere" {
  secret_id = module.secrets.cohere_api_key_secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.cloudrun_sa.email}"

  depends_on = [module.secrets]
}

resource "google_secret_manager_secret_iam_member" "cloudrun_access_db_password" {
  secret_id = module.secrets.db_password_secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.cloudrun_sa.email}"

  depends_on = [module.secrets]
}

# Grant Cloud Run service account Cloud SQL client role
resource "google_project_iam_member" "cloudrun_sql_client" {
  project = var.project_id
  role    = "roles/cloudsql.client"
  member  = "serviceAccount:${google_service_account.cloudrun_sa.email}"
}

# Cloud Run Service for VanCity Lens API
resource "google_cloud_run_service" "api" {
  name     = "vancity-lens-api"
  location = var.region
  project  = var.project_id

  template {
    spec {
      service_account_name = google_service_account.cloudrun_sa.email

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
  service       = google_cloud_run_service.api.name
  location      = google_cloud_run_service.api.location
  role          = "roles/run.invoker"
  member        = "allUsers"

  depends_on = [google_cloud_run_service.api]
}
