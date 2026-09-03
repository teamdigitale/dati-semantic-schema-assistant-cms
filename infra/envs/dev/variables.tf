variable "project_id" {
  description = "Google Cloud project used by the dev environment."
  type        = string
  default     = "istat-ndc-schema-ass-cms-dev"
}

variable "region" {
  description = "Primary Google Cloud region. europe-west8 is Milan."
  type        = string
  default     = "europe-west8"
}

variable "firestore_location" {
  description = "Firestore location. Keep it aligned with the runtime region when possible."
  type        = string
  default     = "europe-west8"
}

variable "environment" {
  description = "Short environment name used in resource names."
  type        = string
  default     = "dev"
}

variable "service_prefix" {
  description = "Prefix shared by the Schema Assistant cloud resources."
  type        = string
  default     = "schema-assistant"
}

variable "developer_invokers" {
  description = "IAM principals allowed to invoke the private dev agent and manual ingestion job."
  type        = list(string)

  validation {
    condition = length(var.developer_invokers) > 0 && alltrue([
      for member in var.developer_invokers :
      can(regex("^(user|group|serviceAccount):", member))
    ])
    error_message = "Use IAM member syntax, for example user:name@example.com."
  }
}

variable "enabled_services" {
  description = "Project APIs managed by Terraform after the one-time Service Usage bootstrap."
  type        = set(string)
  default = [
    "aiplatform.googleapis.com",
    "artifactregistry.googleapis.com",
    "cloudbuild.googleapis.com",
    "cloudresourcemanager.googleapis.com",
    "datastore.googleapis.com",
    "firestore.googleapis.com",
    "iam.googleapis.com",
    "iamcredentials.googleapis.com",
    "logging.googleapis.com",
    "monitoring.googleapis.com",
    "run.googleapis.com",
    "secretmanager.googleapis.com",
    "storage.googleapis.com",
    "sts.googleapis.com",
  ]
}

variable "github_repository" {
  description = "GitHub repository allowed to deploy to dev, in owner/name format."
  type        = string
  default     = "teamdigitale/dati-semantic-schema-assistant-cms"

  validation {
    condition     = can(regex("^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$", var.github_repository))
    error_message = "github_repository must use the owner/name format."
  }
}

variable "github_repository_id" {
  description = "Immutable numeric GitHub repository id allowed to deploy to dev."
  type        = string
  default     = "1288130374"

  validation {
    condition     = can(regex("^[0-9]+$", var.github_repository_id))
    error_message = "github_repository_id must be the numeric id returned by the GitHub API."
  }
}

variable "github_repository_owner_id" {
  description = "Immutable numeric GitHub owner id allowed to deploy to dev."
  type        = string
  default     = "25081492"

  validation {
    condition     = can(regex("^[0-9]+$", var.github_repository_owner_id))
    error_message = "github_repository_owner_id must be the numeric id returned by the GitHub API."
  }
}

variable "github_deploy_branch" {
  description = "Only this branch can exchange GitHub OIDC tokens for dev credentials."
  type        = string
  default     = "main"

  validation {
    condition     = can(regex("^[A-Za-z0-9._/-]+$", var.github_deploy_branch))
    error_message = "github_deploy_branch contains unsupported characters."
  }
}

variable "bucket_name" {
  description = "Optional globally unique bucket name. Empty value derives one from project and environment."
  type        = string
  default     = ""
}

variable "artifact_registry_repository_id" {
  description = "Artifact Registry repository used for the agent and ingestion images."
  type        = string
  default     = "schema-assistant"
}

variable "embedding_vector_dimension" {
  description = "Vertex embedding output dimension stored in Firestore vector indexes."
  type        = number
  default     = 2048

  validation {
    condition     = var.embedding_vector_dimension > 0 && var.embedding_vector_dimension <= 2048
    error_message = "Firestore vector indexes support dimensions from 1 to 2048."
  }
}

variable "agent_image" {
  description = "Bootstrap image for the agent. Application deploys update it outside Terraform."
  type        = string
  default     = "us-docker.pkg.dev/cloudrun/container/hello"
}

variable "web_image" {
  description = "Bootstrap image for the web frontend. Application deploys update it outside Terraform."
  type        = string
  default     = "us-docker.pkg.dev/cloudrun/container/hello"
}

variable "web_frame_ancestors" {
  description = "Exact HTTPS origins allowed to embed the dev web frontend."
  type        = list(string)
  default = [
    "https://wp-ndc-dev.apps.cloudpub.testedev.istat.it",
    "https://wp-ndc-test.apps.cloudpub.testedev.istat.it",
    "https://wp-ndc-prod-blue.apps.cloudpub.istat.it",
    "https://wp-ndc-prod-green.apps.cloudpub.istat.it",
    "https://schema.gov.it",
  ]

  validation {
    condition = alltrue([
      for origin in var.web_frame_ancestors :
      can(regex("^https://[A-Za-z0-9.-]+(:[0-9]{1,5})?$", origin))
    ])
    error_message = "web_frame_ancestors accepts exact HTTPS origins only, without paths, trailing slashes, or wildcards."
  }
}

variable "ingestion_image" {
  description = "Bootstrap image for the ingestion job. Application deploys update it outside Terraform."
  type        = string
  default     = "us-docker.pkg.dev/cloudrun/container/job"
}

variable "force_destroy_bucket" {
  description = "Allows Terraform to delete a non-empty dev bucket. Keep false unless you are intentionally cleaning dev."
  type        = bool
  default     = false
}

variable "firestore_deletion_policy" {
  description = "Terraform behavior on destroy. ABANDON avoids accidental database deletion."
  type        = string
  default     = "ABANDON"

  validation {
    condition     = contains(["ABANDON", "DELETE"], var.firestore_deletion_policy)
    error_message = "Use ABANDON or DELETE."
  }
}

variable "firestore_delete_protection" {
  description = "Firestore delete protection. Dev starts disabled, while Terraform still abandons the database by default."
  type        = bool
  default     = false
}

variable "cloud_run_deletion_protection" {
  description = "Cloud Run deletion protection. Dev starts disabled to keep iteration simple."
  type        = bool
  default     = false
}
