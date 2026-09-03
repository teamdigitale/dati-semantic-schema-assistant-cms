locals {
  cicd_service_account_id   = "${var.service_prefix}-cicd-${var.environment}"
  workload_identity_pool_id = "${var.service_prefix}-github-${var.environment}"
  github_main_ref           = "refs/heads/${var.github_deploy_branch}"
  github_deploy_workflow_refs = [
    "${var.github_repository}/.github/workflows/deploy-dev.yml@${local.github_main_ref}",
    "${var.github_repository}/.github/workflows/deploy-ingestion-dev.yml@${local.github_main_ref}",
  ]

  runtime_service_accounts = toset([
    var.agent_service_account_email,
    var.ingestion_service_account_email,
    var.web_service_account_email,
  ])
}

resource "google_service_account" "cicd" {
  project      = var.project_id
  account_id   = local.cicd_service_account_id
  display_name = "Schema Assistant GitHub CI/CD (${var.environment})"
  description  = "Deploys immutable application images from the authorized GitHub repository."
}

resource "google_iam_workload_identity_pool" "github" {
  project                   = var.project_id
  workload_identity_pool_id = local.workload_identity_pool_id
  display_name              = "Schema Assistant GitHub (${var.environment})"
  description               = "Trust boundary for short-lived GitHub Actions credentials."
}

resource "google_iam_workload_identity_pool_provider" "github" {
  project                            = var.project_id
  workload_identity_pool_id          = google_iam_workload_identity_pool.github.workload_identity_pool_id
  workload_identity_pool_provider_id = "github"
  display_name                       = "GitHub Actions"

  attribute_mapping = {
    "google.subject"                = "assertion.sub"
    "attribute.event_name"          = "assertion.event_name"
    "attribute.ref"                 = "assertion.ref"
    "attribute.repository"          = "assertion.repository"
    "attribute.repository_id"       = "assertion.repository_id"
    "attribute.repository_owner_id" = "assertion.repository_owner_id"
    "attribute.workflow_ref"        = "assertion.workflow_ref"
  }

  # Numeric ids prevent repository name reuse, while workflow_ref limits which
  # reviewed deployment entry points can exchange an OIDC token.
  attribute_condition = join(" && ", [
    "assertion.repository == '${var.github_repository}'",
    "assertion.repository_id == '${var.github_repository_id}'",
    "assertion.repository_owner_id == '${var.github_repository_owner_id}'",
    "assertion.ref == '${local.github_main_ref}'",
    "assertion.event_name in ['push', 'workflow_dispatch']",
    "assertion.workflow_ref in ${jsonencode(local.github_deploy_workflow_refs)}",
  ])

  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }
}

resource "google_service_account_iam_member" "github_impersonates_cicd" {
  service_account_id = google_service_account.cicd.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github.name}/attribute.repository_id/${var.github_repository_id}"
}

resource "google_artifact_registry_repository_iam_member" "cicd_writes_images" {
  project    = var.project_id
  location   = var.region
  repository = var.artifact_registry_repository_id
  role       = "roles/artifactregistry.writer"
  member     = "serviceAccount:${google_service_account.cicd.email}"
}

# This role deliberately omits run.jobs.run, so the pipeline can update the
# ingestion image but cannot start an ingestion execution.
resource "google_project_iam_custom_role" "cicd_cloud_run_deployer" {
  project     = var.project_id
  role_id     = "schemaAssistantCicdDeployer"
  title       = "Schema Assistant CI/CD deployer"
  description = "Updates existing Schema Assistant Cloud Run services and jobs without executing jobs."
  permissions = [
    "run.jobs.get",
    "run.jobs.update",
    "run.services.get",
    "run.services.update",
  ]
}

# Cloud Run updates return a regional operation. This separate read-only role
# lets gcloud wait for that operation without widening update permissions.
resource "google_project_iam_custom_role" "cicd_operation_viewer" {
  project     = var.project_id
  role_id     = "schemaAssistantCicdOperationViewer"
  title       = "Schema Assistant CI/CD operation viewer"
  description = "Reads Cloud Run operation status after a deployment."
  permissions = ["run.operations.get"]
}

resource "google_project_iam_member" "cicd_reads_operations" {
  project = var.project_id
  role    = google_project_iam_custom_role.cicd_operation_viewer.name
  member  = "serviceAccount:${google_service_account.cicd.email}"
}

resource "google_cloud_run_v2_service_iam_member" "cicd_updates_agent" {
  project  = var.project_id
  location = var.region
  name     = var.agent_service_name
  role     = google_project_iam_custom_role.cicd_cloud_run_deployer.name
  member   = "serviceAccount:${google_service_account.cicd.email}"
}

resource "google_cloud_run_v2_service_iam_member" "cicd_updates_web" {
  project  = var.project_id
  location = var.region
  name     = var.web_service_name
  role     = google_project_iam_custom_role.cicd_cloud_run_deployer.name
  member   = "serviceAccount:${google_service_account.cicd.email}"
}

resource "google_cloud_run_v2_job_iam_member" "cicd_updates_ingestion" {
  project  = var.project_id
  location = var.region
  name     = var.ingestion_job_name
  role     = google_project_iam_custom_role.cicd_cloud_run_deployer.name
  member   = "serviceAccount:${google_service_account.cicd.email}"
}

resource "google_service_account_iam_member" "cicd_uses_runtime_identity" {
  for_each = local.runtime_service_accounts

  service_account_id = "projects/${var.project_id}/serviceAccounts/${each.value}"
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.cicd.email}"
}
