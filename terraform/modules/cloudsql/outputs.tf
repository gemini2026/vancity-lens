output "connection_name" {
  description = "Cloud SQL connection name for Cloud SQL Auth proxy"
  value       = google_sql_database_instance.instance.connection_name
}

output "private_ip_address" {
  description = "Private IP address of the Cloud SQL instance"
  value       = google_sql_database_instance.instance.private_ip_address
}

output "database_name" {
  description = "Database name"
  value       = google_sql_database.database.name
}

output "database_user" {
  description = "Database user (password-based, empty when IAM-only)"
  value       = length(google_sql_user.user) > 0 ? google_sql_user.user[0].name : ""
}

output "instance_name" {
  description = "Cloud SQL instance name"
  value       = google_sql_database_instance.instance.name
}

output "iam_database_user" {
  description = "IAM database user name for Cloud SQL IAM auth"
  value       = google_sql_user.iam_user.name
}
