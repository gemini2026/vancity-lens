output "vpc_id" {
  description = "The VPC network ID"
  value       = google_compute_network.vpc.id
}

output "vpc_name" {
  description = "The VPC network name"
  value       = google_compute_network.vpc.name
}

output "subnet_id" {
  description = "The subnet ID"
  value       = google_compute_subnetwork.private.id
}

output "subnet_name" {
  description = "The subnet name"
  value       = google_compute_subnetwork.private.name
}

output "pods_secondary_range" {
  description = "The secondary IP range for pods"
  value       = "10.1.0.0/16"
}

output "services_secondary_range" {
  description = "The secondary IP range for services"
  value       = "10.2.0.0/16"
}
