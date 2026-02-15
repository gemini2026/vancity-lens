# ── Service Account ──────────────────────────────────────────────────────────
resource "google_service_account" "gh_runner" {
  account_id   = "gh-actions-runner"
  display_name = "GitHub Actions Self-Hosted Runner"
  project      = var.project_id
  description  = "Service account for the GCE-based GitHub Actions runner"
}

# ── IAM Roles ────────────────────────────────────────────────────────────────
resource "google_project_iam_member" "runner_artifact_registry" {
  project = var.project_id
  role    = "roles/artifactregistry.writer"
  member  = "serviceAccount:${google_service_account.gh_runner.email}"
}

resource "google_project_iam_member" "runner_container_admin" {
  project = var.project_id
  role    = "roles/container.admin"
  member  = "serviceAccount:${google_service_account.gh_runner.email}"
}

resource "google_project_iam_member" "runner_secret_accessor" {
  project = var.project_id
  role    = "roles/secretmanager.secretAccessor"
  member  = "serviceAccount:${google_service_account.gh_runner.email}"
}

resource "google_project_iam_member" "runner_log_writer" {
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.gh_runner.email}"
}

# ── Firewall: IAP SSH ────────────────────────────────────────────────────────
resource "google_compute_firewall" "iap_ssh_runner" {
  name    = "allow-iap-ssh-gh-runner"
  project = var.project_id
  network = var.network_id

  allow {
    protocol = "tcp"
    ports    = ["22"]
  }

  source_ranges = ["35.235.240.0/20"]
  target_tags   = ["gh-runner"]

  description = "Allow SSH via IAP to GitHub Actions runner"
}

# ── GCE Instance ─────────────────────────────────────────────────────────────
resource "google_compute_instance" "runner" {
  name         = var.runner_name
  machine_type = var.machine_type
  zone         = var.zone
  project      = var.project_id

  tags = ["gh-runner"]

  boot_disk {
    initialize_params {
      image = "ubuntu-os-cloud/ubuntu-2204-lts"
      size  = var.disk_size_gb
      type  = "pd-standard"
    }
  }

  network_interface {
    subnetwork = var.subnet_id
    # No access_config → internal IP only; outbound via Cloud NAT
  }

  service_account {
    email  = google_service_account.gh_runner.email
    scopes = ["cloud-platform"]
  }

  metadata = {
    startup-script = templatefile("${path.module}/startup.sh", {
      GCP_PROJECT_ID             = var.project_id
      GCP_REGION                 = var.region
      GITHUB_REPO                = var.github_repo
      RUNNER_NAME                = var.runner_name
      RUNNER_LABELS              = var.runner_labels
      GITHUB_RUNNER_TOKEN_SECRET = var.github_runner_token_secret_id
    })
  }

  shielded_instance_config {
    enable_secure_boot          = true
    enable_vtpm                 = true
    enable_integrity_monitoring = true
  }

  scheduling {
    automatic_restart   = true
    on_host_maintenance = "MIGRATE"
  }

  allow_stopping_for_update = true

  depends_on = [
    google_project_iam_member.runner_secret_accessor,
  ]
}
