output "cluster_name" {
  value = google_container_cluster.small.name
}

output "cluster_zone" {
  value = google_container_cluster.small.location
}
