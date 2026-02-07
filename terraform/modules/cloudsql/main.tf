# Cloud SQL PostgreSQL Instance
resource "google_sql_database_instance" "instance" {
  name             = "vancity-lens-db"
  project          = var.project_id
  region           = var.region
  database_version = "POSTGRES_16"
  deletion_protection = false

  settings {
    tier              = "db-f1-micro"
    availability_type = "ZONAL"
    disk_type         = "PD_SSD"
    disk_size         = 10

    backup_configuration {
      enabled                        = true
      start_time                     = "03:00"
      transaction_log_retention_days = 7
    }

    ip_configuration {
      require_ssl = false
      dynamic "authorized_networks" {
        for_each = []
        content {
          name  = authorized_networks.value.name
          value = authorized_networks.value.cidr
        }
      }
    }

    database_flags {
      name  = "shared_preload_libraries"
      value = "pgvector,postgis"
    }

    database_flags {
      name  = "max_connections"
      value = "100"
    }

    database_flags {
      name  = "log_min_duration_statement"
      value = "1000"
    }

    insights_config {
      query_insights_enabled  = true
      query_string_length     = 1024
      record_application_tags = true
    }

    user_labels = {
      app         = "vancity-lens"
      environment = "poc"
    }
  }

  depends_on = [google_service_networking_connection.private_vpc_connection]
}

# Enable private IP
resource "google_sql_database_instance" "instance_private_ip" {
  provider = google-beta

  name = google_sql_database_instance.instance.name
  region = var.region

  settings {
    ip_configuration {
      ipv4_enabled    = false
      private_network = var.network_id
      require_ssl     = false
    }
  }

  depends_on = [google_service_networking_connection.private_vpc_connection]
}

# Service Networking Connection for private IP
resource "google_service_networking_connection" "private_vpc_connection" {
  network                 = var.network_id
  service                 = "servicenetworking.googleapis.com"
  reserved_peering_ranges = [google_compute_global_address.private_ip_address.name]
}

# Reserved IP range for private service connection
resource "google_compute_global_address" "private_ip_address" {
  name          = "private-ip-address"
  purpose       = "VPC_PEERING"
  address_type  = "INTERNAL"
  prefix_length = 16
  network       = var.network_id
  project       = var.project_id
}

# PostgreSQL Database
resource "google_sql_database" "database" {
  name     = "vancity_lens"
  instance = google_sql_database_instance.instance.name
  project  = var.project_id
}

# PostgreSQL User
resource "google_sql_user" "user" {
  name     = "vancity"
  instance = google_sql_database_instance.instance.name
  password = var.db_password
  project  = var.project_id
}

# Install pgvector extension
resource "google_sql_database_instance_additional_database" "pgvector" {
  instance = google_sql_database_instance.instance.name
  name     = "pgvector_enabled"

  depends_on = [google_sql_database.database]
}
