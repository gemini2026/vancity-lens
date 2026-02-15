output "runner_instance_name" {
  description = "GCE instance name of the GitHub Actions runner"
  value       = google_compute_instance.runner.name
}

output "runner_internal_ip" {
  description = "Internal IP address of the runner instance"
  value       = google_compute_instance.runner.network_interface[0].network_ip
}

output "runner_service_account_email" {
  description = "Service account email used by the runner"
  value       = google_service_account.gh_runner.email
}
