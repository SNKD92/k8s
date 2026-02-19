resource "google_container_cluster" "small" {
  name     = "small-gke"
  location = var.zone

  deletion_protection = false

  initial_node_count = 1

  node_config {
    machine_type = "e2-small"
    preemptible  = true
    oauth_scopes = ["https://www.googleapis.com/auth/cloud-platform"]
  }

  ip_allocation_policy {}
}
