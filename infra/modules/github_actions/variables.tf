variable "project_id" {
  description = "Google Cloud project id."
  type        = string
}

variable "region" {
  description = "Cloud Run and Artifact Registry region."
  type        = string
}

variable "environment" {
  description = "Environment name used in identity resource names."
  type        = string
}

variable "service_prefix" {
  description = "Prefix shared by Schema Assistant resources."
  type        = string
}

variable "artifact_registry_repository_id" {
  description = "Artifact Registry repository that receives application images."
  type        = string
}

variable "github_repository" {
  description = "Allowed GitHub repository in owner/name format."
  type        = string
}

variable "github_repository_id" {
  description = "Immutable numeric id of the allowed GitHub repository."
  type        = string
}

variable "github_repository_owner_id" {
  description = "Immutable numeric id of the allowed GitHub repository owner."
  type        = string
}

variable "github_deploy_branch" {
  description = "Branch allowed to request deploy credentials."
  type        = string
}

variable "agent_service_name" {
  description = "Private Cloud Run agent service updated by CI/CD."
  type        = string
}

variable "web_service_name" {
  description = "Public Cloud Run web service updated by CI/CD."
  type        = string
}

variable "ingestion_job_name" {
  description = "Manual Cloud Run ingestion job updated by CI/CD."
  type        = string
}

variable "agent_service_account_email" {
  description = "Runtime service account used by the private agent."
  type        = string
}

variable "ingestion_service_account_email" {
  description = "Runtime service account used by the ingestion job."
  type        = string
}

variable "web_service_account_email" {
  description = "Runtime service account used by the public web service."
  type        = string
}
