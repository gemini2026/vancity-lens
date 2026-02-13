locals {
  common_labels = {
    app         = "vancity-lens"
    environment = var.environment_name
  }
}

# Secret Manager for API keys and runtime configuration.

# Anthropic API Key
resource "google_secret_manager_secret" "anthropic_api_key" {
  secret_id = "anthropic-api-key"
  project   = var.project_id

  replication {
    auto {}
  }

  labels = merge(local.common_labels, { service = "llm" })
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
    auto {}
  }

  labels = merge(local.common_labels, { service = "embeddings" })
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
    auto {}
  }

  labels = merge(local.common_labels, { service = "database" })
}

resource "google_secret_manager_secret_version" "db_password_version" {
  secret      = google_secret_manager_secret.db_password.id
  secret_data = var.db_password
}

# Database URL for app runtime.
resource "google_secret_manager_secret" "database_url" {
  secret_id = "database-url"
  project   = var.project_id

  replication {
    auto {}
  }

  labels = merge(local.common_labels, { service = "database" })
}

resource "google_secret_manager_secret_version" "database_url_version" {
  count = trimspace(var.database_url) == "" ? 0 : 1

  secret      = google_secret_manager_secret.database_url.id
  secret_data = var.database_url
}

# K2 API Key.
resource "google_secret_manager_secret" "k2_api_key" {
  secret_id = "k2-api-key"
  project   = var.project_id

  replication {
    auto {}
  }

  labels = merge(local.common_labels, { service = "k2" })
}

resource "google_secret_manager_secret_version" "k2_api_key_version" {
  count = trimspace(var.k2_api_key) == "" ? 0 : 1

  secret      = google_secret_manager_secret.k2_api_key.id
  secret_data = var.k2_api_key
}

# Brave Search API Key.
resource "google_secret_manager_secret" "brave_search_api_key" {
  secret_id = "brave-search-api-key"
  project   = var.project_id

  replication {
    auto {}
  }

  labels = merge(local.common_labels, { service = "search" })
}

resource "google_secret_manager_secret_version" "brave_search_api_key_version" {
  count = trimspace(var.brave_search_api_key) == "" ? 0 : 1

  secret      = google_secret_manager_secret.brave_search_api_key.id
  secret_data = var.brave_search_api_key
}

# Admin API Key.
resource "google_secret_manager_secret" "admin_api_key" {
  secret_id = "admin-api-key"
  project   = var.project_id

  replication {
    auto {}
  }

  labels = merge(local.common_labels, { service = "admin" })
}

resource "google_secret_manager_secret_version" "admin_api_key_version" {
  count = trimspace(var.admin_api_key) == "" ? 0 : 1

  secret      = google_secret_manager_secret.admin_api_key.id
  secret_data = var.admin_api_key
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

resource "google_secret_manager_secret_iam_member" "gke_access_database_url" {
  secret_id = google_secret_manager_secret.database_url.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${var.gke_service_account}"

  depends_on = [google_secret_manager_secret.database_url]
}

resource "google_secret_manager_secret_iam_member" "gke_access_k2_api_key" {
  secret_id = google_secret_manager_secret.k2_api_key.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${var.gke_service_account}"

  depends_on = [google_secret_manager_secret.k2_api_key]
}

resource "google_secret_manager_secret_iam_member" "gke_access_brave_search_api_key" {
  secret_id = google_secret_manager_secret.brave_search_api_key.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${var.gke_service_account}"

  depends_on = [google_secret_manager_secret.brave_search_api_key]
}

resource "google_secret_manager_secret_iam_member" "gke_access_admin_api_key" {
  secret_id = google_secret_manager_secret.admin_api_key.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${var.gke_service_account}"

  depends_on = [google_secret_manager_secret.admin_api_key]
}
