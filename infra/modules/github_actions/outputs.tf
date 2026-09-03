output "service_account_email" {
  value = google_service_account.cicd.email
}

output "workload_identity_pool_name" {
  value = google_iam_workload_identity_pool.github.name
}

output "workload_identity_provider_name" {
  value = google_iam_workload_identity_pool_provider.github.name
}

output "cloud_run_deployer_role_name" {
  value = google_project_iam_custom_role.cicd_cloud_run_deployer.name
}

output "cloud_run_operation_viewer_role_name" {
  value = google_project_iam_custom_role.cicd_operation_viewer.name
}
