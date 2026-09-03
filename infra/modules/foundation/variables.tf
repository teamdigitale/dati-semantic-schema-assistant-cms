variable "project_id" {
  description = "Google Cloud project id."
  type        = string
}

variable "project_number" {
  description = "Numeric Google Cloud project identifier."
  type        = string
}

variable "region" {
  description = "Primary Google Cloud region."
  type        = string
}

variable "environment" {
  description = "Environment name."
  type        = string
}

variable "service_prefix" {
  description = "Prefix shared by Schema Assistant resources."
  type        = string
}

variable "labels" {
  description = "Labels applied to supported resources."
  type        = map(string)
}

variable "bucket_name" {
  description = "Optional bucket name. Empty value derives a name from project and environment."
  type        = string
}

variable "artifact_registry_repository_id" {
  description = "Artifact Registry repository id."
  type        = string
}

variable "embedding_vector_dimension" {
  description = "Dimension used by Vertex embeddings and Firestore vector indexes."
  type        = number
}

variable "firestore_location" {
  description = "Firestore database location."
  type        = string
}

variable "firestore_deletion_policy" {
  description = "Terraform destroy behavior for Firestore."
  type        = string
}

variable "firestore_delete_protection" {
  description = "Whether Firestore delete protection is enabled."
  type        = bool
}

variable "force_destroy_bucket" {
  description = "Whether Terraform can delete a non-empty bucket."
  type        = bool
}
