# Artifact Registry Repository for Docker images
resource "google_artifact_registry_repository" "docker_repo" {
  location      = var.region
  repository_id = "vancity-lens-docker"
  description   = "Docker repository for VanCity Lens FastAPI backend"
  format        = "DOCKER"
  project       = var.project_id

  labels = {
    app         = "vancity-lens"
    environment = "poc"
  }
}

# IAM binding to allow GKE to pull images
resource "google_artifact_registry_repository_iam_member" "gke_pull" {
  location   = google_artifact_registry_repository.docker_repo.location
  repository = google_artifact_registry_repository.docker_repo.name
  role       = "roles/artifactregistry.reader"
  member     = "serviceAccount:${var.gke_service_account}"

  depends_on = [google_artifact_registry_repository.docker_repo]
}
