# GKE Cluster
resource "google_container_cluster" "primary" {
  name       = var.cluster_name
  project    = var.project_id
  location   = var.region
  network    = var.network_id
  subnetwork = var.subnet_id
  # Required by GKE API when using separately managed node pools.
  initial_node_count       = 1
  remove_default_node_pool = true

  # Standard cluster settings
  enable_shielded_nodes = true

  # Private cluster configuration
  private_cluster_config {
    enable_private_nodes    = true
    enable_private_endpoint = false
    master_ipv4_cidr_block  = "172.16.0.0/28"
  }

  # Master authorized networks - allow access from specific IPs
  master_authorized_networks_config {
    cidr_blocks {
      cidr_block   = "0.0.0.0/0"
      display_name = "All networks"
    }
  }

  # Network policy
  network_policy {
    enabled = true
  }

  # IP allocation policy for secondary ranges
  ip_allocation_policy {
    cluster_secondary_range_name  = "pods"
    services_secondary_range_name = "services"
  }

  # Workload Identity
  workload_identity_config {
    workload_pool = "${var.project_id}.svc.id.goog"
  }

  # Logging and monitoring
  logging_service    = "logging.googleapis.com/kubernetes"
  monitoring_service = "monitoring.googleapis.com/kubernetes"

  # Maintenance window
  maintenance_policy {
    daily_maintenance_window {
      start_time = "03:00"
    }
  }

  # Resource labels
  resource_labels = {
    app         = "vancity-lens"
    environment = "poc"
  }

}
# Node pool configuration
resource "google_container_node_pool" "primary_nodes" {
  name       = "primary-node-pool"
  cluster    = google_container_cluster.primary.id
  node_count = 1
  project    = var.project_id

  autoscaling {
    min_node_count = 1
    max_node_count = 3
  }

  management {
    auto_repair  = true
    auto_upgrade = true
  }

  node_config {
    preemptible  = false
    machine_type = "e2-medium"

    disk_size_gb = 50
    disk_type    = "pd-standard"

    oauth_scopes = [
      "https://www.googleapis.com/auth/cloud-platform"
    ]

    tags = ["gke-node", "vancity-lens"]

    labels = {
      app         = "vancity-lens"
      environment = "poc"
    }

    workload_metadata_config {
      mode = "GKE_METADATA"
    }

    shielded_instance_config {
      enable_secure_boot          = true
      enable_integrity_monitoring = true
    }
  }

  depends_on = [google_container_cluster.primary]
}

# Separately Managed Node Pool for workloads
resource "google_container_node_pool" "backend" {
  name    = "backend-node-pool"
  cluster = google_container_cluster.primary.id
  project = var.project_id

  autoscaling {
    min_node_count = 1
    max_node_count = 5
  }

  management {
    auto_repair  = true
    auto_upgrade = true
  }

  node_config {
    preemptible  = false
    machine_type = "e2-medium"

    disk_size_gb = 50
    disk_type    = "pd-standard"

    oauth_scopes = [
      "https://www.googleapis.com/auth/cloud-platform"
    ]

    tags = ["gke-backend", "vancity-lens"]

    labels = {
      workload    = "backend"
      app         = "vancity-lens"
      environment = "poc"
    }

    workload_metadata_config {
      mode = "GKE_METADATA"
    }

    shielded_instance_config {
      enable_secure_boot          = true
      enable_integrity_monitoring = true
    }

    taint {
      key    = "workload"
      value  = "backend"
      effect = "NO_SCHEDULE"
    }
  }

  depends_on = [google_container_cluster.primary]
}
