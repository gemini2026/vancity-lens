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
