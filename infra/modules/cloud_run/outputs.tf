output "agent_service_name" {
  value = google_cloud_run_v2_service.agent.name
}

output "agent_url" {
  value = google_cloud_run_v2_service.agent.uri
}

output "web_service_name" {
  value = google_cloud_run_v2_service.web.name
}

output "web_url" {
  value = google_cloud_run_v2_service.web.uri
}

output "ingestion_job_name" {
  value = google_cloud_run_v2_job.ingestion.name
}
