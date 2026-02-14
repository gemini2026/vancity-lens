output "anthropic_api_key_secret_id" {
  description = "Secret ID for Anthropic API key"
  value       = google_secret_manager_secret.anthropic_api_key.id
}

output "cohere_api_key_secret_id" {
  description = "Secret ID for Cohere API key"
  value       = google_secret_manager_secret.cohere_api_key.id
}

output "db_password_secret_id" {
  description = "Secret ID for database password"
  value       = google_secret_manager_secret.db_password.id
}

output "database_url_secret_id" {
  description = "Secret ID for database URL"
  value       = google_secret_manager_secret.database_url.id
}

output "k2_api_key_secret_id" {
  description = "Secret ID for K2 API key"
  value       = google_secret_manager_secret.k2_api_key.id
}

output "brave_search_api_key_secret_id" {
  description = "Secret ID for Brave Search API key"
  value       = google_secret_manager_secret.brave_search_api_key.id
}

output "admin_api_key_secret_id" {
  description = "Secret ID for admin API key"
  value       = google_secret_manager_secret.admin_api_key.id
}
