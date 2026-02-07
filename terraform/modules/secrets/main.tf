# Secret Manager for API Keys

# Anthropic API Key
resource "google_secret_manager_secret" "anthropic_api_key" {
  secret_id = "anthropic-api-key"
  project   = var.project_id

  replication {
    automatic = true
  }

  labels = {
    app         = "vancity-lens"
    environment = "poc"
    service     = "llm"
  }
}

resource "google_secret_manager_secret_version" "anthropic_api_key_version" {
  secret      = google_secret_manager_secret.anthropic_api_key.id
  secret_data = var.anthropic_api_key
}

# Cohere API Key
resource "google_secret_manager_secret" "cohere_api_key" {
  secret_id = "cohere-api-key"
  project   = var.project_id

  replication {
    automatic = true
  }

  labels = {
    app         = "vancity-lens"
    environment = "poc"
    service     = "embeddings"
  }
}

resource "google_secret_manager_secret_version" "cohere_api_key_version" {
  secret      = google_secret_manager_secret.cohere_api_key.id
  secret_data = var.cohere_api_key
}

# Database Password
resource "google_secret_manager_secret" "db_password" {
  secret_id = "database-password"
  project   = var.project_id

  replication {
    automatic = true
  }

  labels = {
    app         = "vancity-lens"
    environment = "poc"
    service     = "database"
  }
}

resource "google_secret_manager_secret_version" "db_password_version" {
  secret      = google_secret_manager_secret.db_password.id
  secret_data = var.db_password
}

# IAM binding to allow GKE service account to read secrets
resource "google_secret_manager_secret_iam_member" "gke_access_anthropic" {
  secret_id = google_secret_manager_secret.anthropic_api_key.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${var.gke_service_account}"

  depends_on = [google_secret_manager_secret.anthropic_api_key]
}

resource "google_secret_manager_secret_iam_member" "gke_access_cohere" {
  secret_id = google_secret_manager_secret.cohere_api_key.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${var.gke_service_account}"

  depends_on = [google_secret_manager_secret.cohere_api_key]
}

resource "google_secret_manager_secret_iam_member" "gke_access_db_password" {
  secret_id = google_secret_manager_secret.db_password.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${var.gke_service_account}"

  depends_on = [google_secret_manager_secret.db_password]
}
