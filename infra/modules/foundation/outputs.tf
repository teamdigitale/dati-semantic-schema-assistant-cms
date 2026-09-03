output "artifact_registry_repository_name" {
  value = google_artifact_registry_repository.containers.name
}

output "artifact_registry_repository_url" {
  value = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.containers.repository_id}"
}

output "bucket_name" {
  value = google_storage_bucket.data.name
}

output "firestore_database_name" {
  value = google_firestore_database.default.name
}

output "agent_service_account_email" {
  value = google_service_account.agent.email
}

output "ingestion_service_account_email" {
  value = google_service_account.ingestion.email
}

output "web_service_account_email" {
  value = google_service_account.web.email
}

output "cloud_build_default_service_account_email" {
  value = local.cloud_build_default_service_account
}
