variable "project_id" {
  description = "Google Cloud project id."
  type        = string
}

variable "region" {
  description = "Cloud Run region."
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

variable "agent_image" {
  description = "Agent container image."
  type        = string
}

variable "web_image" {
  description = "Web frontend container image."
  type        = string
}

variable "web_frame_ancestors" {
  description = "Exact HTTPS origins allowed to embed the public web frontend."
  type        = list(string)
  default     = []

  validation {
    condition = alltrue([
      for origin in var.web_frame_ancestors :
      can(regex("^https://[A-Za-z0-9.-]+(:[0-9]{1,5})?$", origin))
    ])
    error_message = "web_frame_ancestors accepts exact HTTPS origins only, without paths, trailing slashes, or wildcards."
  }
}

variable "ingestion_image" {
  description = "Ingestion job container image."
  type        = string
}

variable "agent_service_account_email" {
  description = "Service account used by the agent."
  type        = string
}

variable "ingestion_service_account_email" {
  description = "Service account used by the ingestion job."
  type        = string
}

variable "web_service_account_email" {
  description = "Service account used by the public web frontend."
  type        = string
}

variable "bucket_name" {
  description = "Application data bucket."
  type        = string
}

variable "firestore_database_name" {
  description = "Firestore database id."
  type        = string
}

variable "developer_invokers" {
  description = "IAM members allowed to invoke dev Cloud Run resources."
  type        = list(string)
}

variable "deletion_protection" {
  description = "Cloud Run deletion protection."
  type        = bool
}
