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
