output "project_id" {
  value = var.project_id
}

output "region" {
  value = var.region
}

output "artifact_registry_repository" {
  value = module.foundation.artifact_registry_repository_name
}

output "artifact_registry_repository_url" {
  value = module.foundation.artifact_registry_repository_url
}

output "bucket_name" {
  value = module.foundation.bucket_name
}

output "firestore_database_name" {
  value = module.foundation.firestore_database_name
}

output "agent_service_account_email" {
  value = module.foundation.agent_service_account_email
}

output "ingestion_service_account_email" {
  value = module.foundation.ingestion_service_account_email
}

output "web_service_account_email" {
  value = module.foundation.web_service_account_email
}

output "cloud_build_default_service_account_email" {
  value = module.foundation.cloud_build_default_service_account_email
}

output "agent_service_name" {
  value = module.cloud_run.agent_service_name
}

output "agent_url" {
  value = module.cloud_run.agent_url
}

output "web_service_name" {
  value = module.cloud_run.web_service_name
}

output "web_url" {
  value = module.cloud_run.web_url
}

output "ingestion_job_name" {
  value = module.cloud_run.ingestion_job_name
}

output "github_actions_service_account_email" {
  value = module.github_actions.service_account_email
}

output "github_actions_workload_identity_provider" {
  value = module.github_actions.workload_identity_provider_name
}

output "github_actions_repository" {
  value = var.github_repository
}
