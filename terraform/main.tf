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
