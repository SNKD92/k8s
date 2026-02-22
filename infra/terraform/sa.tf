# -----------------------------
# Service Account
# -----------------------------
resource "google_service_account" "github_actions" {
  account_id   = "github-actions"
  display_name = "GitHub Actions Service Account"
}

# -----------------------------
# IAM Roles for GKE Deployment
# -----------------------------
resource "google_project_iam_member" "github_actions_container_developer" {
  project = var.project_id
  role    = "roles/container.developer"
  member  = "serviceAccount:${google_service_account.github_actions.email}"
}

resource "google_project_iam_member" "github_actions_cluster_viewer" {
  project = var.project_id
  role    = "roles/container.clusterViewer"
  member  = "serviceAccount:${google_service_account.github_actions.email}"
}

# -----------------------------
# Workload Identity Pool
# -----------------------------
resource "google_iam_workload_identity_pool" "github_pool" {
  workload_identity_pool_id = "github-pool"
  display_name              = "GitHub Actions Pool"
  description               = "OIDC pool for GitHub Actions"
}

# -----------------------------
# GitHub OIDC Provider
# -----------------------------
resource "google_iam_workload_identity_pool_provider" "github_provider" {
  workload_identity_pool_id          = google_iam_workload_identity_pool.github_pool.workload_identity_pool_id
  workload_identity_pool_provider_id = "github-provider"
  display_name                       = "GitHub Provider"
  description                        = "OIDC provider for GitHub Actions"

  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }

  attribute_mapping = {
    "google.subject"       = "assertion.sub"
    "attribute.actor"      = "assertion.actor"
    "attribute.repository" = "assertion.repository"
    "attribute.ref"        = "assertion.ref"
  }

  # Correct restriction to your repo
  attribute_condition = "assertion.repository == \"SNKD92/k8s\""

  depends_on = [
    google_iam_workload_identity_pool.github_pool
  ]
}

# -----------------------------
# Allow GitHub repo to impersonate Service Account
# -----------------------------
resource "google_service_account_iam_member" "github_actions_identity" {
  service_account_id = google_service_account.github_actions.name
  role               = "roles/iam.workloadIdentityUser"

  member = "principalSet://iam.googleapis.com/projects/365212276900/locations/global/workloadIdentityPools/github-pool/attribute.repository/SNKD92/k8s"

  depends_on = [
    google_iam_workload_identity_pool_provider.github_provider
  ]
}