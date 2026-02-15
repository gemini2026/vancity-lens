output "vpc_id" {
  description = "VPC Network ID"
  value       = module.network.vpc_id
}

output "vpc_name" {
  description = "VPC Network name"
  value       = module.network.vpc_name
}

output "subnet_name" {
  description = "Subnet name"
  value       = module.network.subnet_name
}

output "subnet_id" {
  description = "Subnet ID"
  value       = module.network.subnet_id
}

output "gke_cluster_name" {
  description = "GKE Cluster name"
  value       = module.gke.cluster_name
}

output "gke_cluster_endpoint" {
  description = "GKE Cluster endpoint"
  value       = module.gke.cluster_endpoint
  sensitive   = true
}

output "gke_cluster_ca_certificate" {
  description = "GKE Cluster CA certificate"
  value       = module.gke.cluster_ca_certificate
  sensitive   = true
}

output "gke_location" {
  description = "GKE Cluster location"
  value       = module.gke.location
}

output "gke_workload_identity_pool" {
  description = "GKE Workload Identity pool"
  value       = module.gke.workload_identity_pool
}

output "cloudsql_connection_name" {
  description = "Cloud SQL connection name for proxy"
  value       = module.cloudsql.connection_name
}

output "cloudsql_private_ip" {
  description = "Cloud SQL private IP address"
  value       = module.cloudsql.private_ip_address
}

output "cloudsql_database_name" {
  description = "Cloud SQL database name"
  value       = module.cloudsql.database_name
}

output "cloudsql_database_user" {
  description = "Cloud SQL database user"
  value       = module.cloudsql.database_user
}

output "cloudsql_instance_name" {
  description = "Cloud SQL instance name"
  value       = module.cloudsql.instance_name
}

output "artifact_registry_repository_url" {
  description = "Artifact Registry repository URL"
  value       = module.registry.repository_url
}

output "artifact_registry_repository_name" {
  description = "Artifact Registry repository name"
  value       = module.registry.repository_name
}

output "gke_service_account_email" {
  description = "GKE service account email"
  value       = google_service_account.gke_sa.email
}

output "anthropic_secret_id" {
  description = "Secret Manager ID for Anthropic API key"
  value       = module.secrets.anthropic_api_key_secret_id
}

output "cohere_secret_id" {
  description = "Secret Manager ID for Cohere API key"
  value       = module.secrets.cohere_api_key_secret_id
}

output "db_password_secret_id" {
  description = "Secret Manager ID for database password"
  value       = module.secrets.db_password_secret_id
}

output "database_url_secret_id" {
  description = "Secret Manager ID for database URL"
  value       = module.secrets.database_url_secret_id
}

output "k2_api_key_secret_id" {
  description = "Secret Manager ID for K2 API key"
  value       = module.secrets.k2_api_key_secret_id
}

output "brave_search_api_key_secret_id" {
  description = "Secret Manager ID for Brave Search API key"
  value       = module.secrets.brave_search_api_key_secret_id
}

output "admin_api_key_secret_id" {
  description = "Secret Manager ID for admin API key"
  value       = module.secrets.admin_api_key_secret_id
}

output "document_archive_bucket_name" {
  description = "Document archive bucket name"
  value       = module.storage.archive_bucket_name
}

output "document_archive_bucket_url" {
  description = "Document archive bucket URL"
  value       = module.storage.archive_bucket_url
}

output "document_long_term_bucket_name" {
  description = "Document long-term retention bucket name"
  value       = module.storage.long_term_bucket_name
}

output "document_long_term_bucket_url" {
  description = "Document long-term retention bucket URL"
  value       = module.storage.long_term_bucket_url
}

output "observability_log_bucket_id" {
  description = "Cloud Logging bucket id"
  value       = module.observability.log_bucket_id
}

output "observability_log_archive_sink_name" {
  description = "Cloud Logging sink name to GCS archive"
  value       = module.observability.log_archive_sink_name
}

output "observability_app_uptime_check_id" {
  description = "App uptime check id when enabled"
  value       = module.observability.app_uptime_check_id
}

output "observability_api_uptime_check_id" {
  description = "API uptime check id when enabled"
  value       = module.observability.api_uptime_check_id
}

output "runner_instance_name" {
  description = "GitHub Actions runner GCE instance name"
  value       = module.gh_runner.runner_instance_name
}

output "runner_internal_ip" {
  description = "GitHub Actions runner internal IP address"
  value       = module.gh_runner.runner_internal_ip
}

output "runner_service_account_email" {
  description = "GitHub Actions runner service account email"
  value       = module.gh_runner.runner_service_account_email
}

output "cloudrun_service_name" {
  description = "Cloud Run service name"
  value       = try(google_cloud_run_service.api[0].name, null)
}

output "cloudrun_service_url" {
  description = "Cloud Run service URL"
  value       = try(google_cloud_run_service.api[0].status[0].url, null)
  sensitive   = true
}

output "cloudrun_service_account_email" {
  description = "Cloud Run service account email"
  value       = try(google_service_account.cloudrun_sa[0].email, null)
}

output "cloudflare_app_hostname" {
  description = "Cloudflare app hostname when Cloudflare module is enabled"
  value       = try(module.cloudflare[0].app_hostname, null)
}

output "cloudflare_api_hostname" {
  description = "Cloudflare API hostname when Cloudflare module is enabled"
  value       = try(module.cloudflare[0].api_hostname, null)
}

output "cloudflare_staging_hostname" {
  description = "Cloudflare staging hostname when configured"
  value       = try(module.cloudflare[0].staging_hostname, null)
}
