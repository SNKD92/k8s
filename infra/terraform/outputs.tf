output "cluster_name" {
  value = google_container_cluster.small.name
}

output "cluster_zone" {
  value = google_container_cluster.small.location
}

output "github_actions_service_account_email" {
  value = google_service_account.github_actions.email
}