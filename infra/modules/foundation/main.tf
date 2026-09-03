locals {
  derived_bucket_name = "${var.project_id}-${var.service_prefix}-${var.environment}-data"
  bucket_name         = var.bucket_name != "" ? var.bucket_name : local.derived_bucket_name
  cloud_build_default_service_account = (
    "${var.project_number}-compute@developer.gserviceaccount.com"
  )

  agent_project_roles = [
    "roles/aiplatform.user",
    "roles/datastore.user",
    "roles/logging.logWriter",
    "roles/monitoring.metricWriter",
  ]

  ingestion_project_roles = [
    "roles/aiplatform.user",
    "roles/datastore.user",
    "roles/logging.logWriter",
    "roles/monitoring.metricWriter",
  ]

  web_project_roles = [
    "roles/logging.logWriter",
    "roles/monitoring.metricWriter",
  ]

  service_account_roles = flatten([
    for item in [
      {
        email = google_service_account.agent.email
        roles = local.agent_project_roles
      },
      {
        email = google_service_account.ingestion.email
        roles = local.ingestion_project_roles
      },
      {
        email = google_service_account.web.email
        roles = local.web_project_roles
      }
      ] : [
      for role in item.roles : {
        key   = "${item.email}-${role}"
        email = item.email
        role  = role
      }
    ]
  ])
}

resource "google_artifact_registry_repository" "containers" {
  project       = var.project_id
  location      = var.region
  repository_id = var.artifact_registry_repository_id
  description   = "Container images for Schema Assistant dev workloads"
  format        = "DOCKER"
  labels        = var.labels
}

resource "google_storage_bucket" "data" {
  project                     = var.project_id
  name                        = local.bucket_name
  location                    = upper(var.region)
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = var.force_destroy_bucket
  labels                      = var.labels

  versioning {
    enabled = true
  }

  lifecycle_rule {
    action {
      type = "Delete"
    }

    condition {
      age        = 30
      with_state = "ARCHIVED"
    }
  }
}

resource "google_firestore_database" "default" {
  project     = var.project_id
  name        = "(default)"
  location_id = var.firestore_location
  type        = "FIRESTORE_NATIVE"

  delete_protection_state = var.firestore_delete_protection ? "DELETE_PROTECTION_ENABLED" : "DELETE_PROTECTION_DISABLED"
  deletion_policy         = var.firestore_deletion_policy
}

resource "google_firestore_index" "rag_chunks_vector" {
  project     = var.project_id
  database    = google_firestore_database.default.name
  collection  = "chunks"
  query_scope = "COLLECTION_GROUP"

  fields {
    field_path = "__name__"
    order      = "ASCENDING"
  }

  fields {
    field_path = "embedding"

    vector_config {
      dimension = var.embedding_vector_dimension

      flat {}
    }
  }
}

# These indexes keep vector searches inside the entity and resource selected by
# the routing layer. They avoid fetching global nearest neighbours and filtering
# them only after the query has completed.
resource "google_firestore_index" "rag_chunks_entity_vector" {
  project     = var.project_id
  database    = google_firestore_database.default.name
  collection  = "chunks"
  query_scope = "COLLECTION_GROUP"

  fields {
    field_path = "entity_id"
    order      = "ASCENDING"
  }

  fields {
    field_path = "__name__"
    order      = "ASCENDING"
  }

  fields {
    field_path = "embedding"

    vector_config {
      dimension = var.embedding_vector_dimension

      flat {}
    }
  }
}

resource "google_firestore_index" "rag_chunks_resource_vector" {
  project     = var.project_id
  database    = google_firestore_database.default.name
  collection  = "chunks"
  query_scope = "COLLECTION_GROUP"

  fields {
    field_path = "resource_id"
    order      = "ASCENDING"
  }

  fields {
    field_path = "__name__"
    order      = "ASCENDING"
  }

  fields {
    field_path = "embedding"

    vector_config {
      dimension = var.embedding_vector_dimension

      flat {}
    }
  }
}

resource "google_firestore_index" "rag_chunks_entity_resource_vector" {
  project     = var.project_id
  database    = google_firestore_database.default.name
  collection  = "chunks"
  query_scope = "COLLECTION_GROUP"

  fields {
    field_path = "entity_id"
    order      = "ASCENDING"
  }

  fields {
    field_path = "resource_id"
    order      = "ASCENDING"
  }

  fields {
    field_path = "__name__"
    order      = "ASCENDING"
  }

  fields {
    field_path = "embedding"

    vector_config {
      dimension = var.embedding_vector_dimension

      flat {}
    }
  }
}

resource "google_service_account" "agent" {
  project      = var.project_id
  account_id   = "${var.service_prefix}-agent-${var.environment}"
  display_name = "Schema Assistant agent (${var.environment})"
  description  = "Runs the private chat agent on Cloud Run."
}

resource "google_service_account" "ingestion" {
  project      = var.project_id
  account_id   = "${var.service_prefix}-ingestion-${var.environment}"
  display_name = "Schema Assistant ingestion (${var.environment})"
  description  = "Runs the manual ingestion job on Cloud Run."
}

resource "google_service_account" "web" {
  project      = var.project_id
  account_id   = "${var.service_prefix}-web-${var.environment}"
  display_name = "Schema Assistant web (${var.environment})"
  description  = "Runs the public web frontend on Cloud Run."
}

resource "google_project_iam_member" "runtime_roles" {
  for_each = {
    for item in local.service_account_roles : item.key => item
  }

  project = var.project_id
  role    = each.value.role
  member  = "serviceAccount:${each.value.email}"
}

resource "google_storage_bucket_iam_member" "agent_reads_data" {
  bucket = google_storage_bucket.data.name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${google_service_account.agent.email}"
}

resource "google_storage_bucket_iam_member" "ingestion_writes_data" {
  bucket = google_storage_bucket.data.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.ingestion.email}"
}

resource "google_project_iam_member" "cloud_build_builder" {
  project = var.project_id
  role    = "roles/cloudbuild.builds.builder"
  member  = "serviceAccount:${local.cloud_build_default_service_account}"
}

resource "google_artifact_registry_repository_iam_member" "cloud_build_pushes_images" {
  project    = var.project_id
  location   = google_artifact_registry_repository.containers.location
  repository = google_artifact_registry_repository.containers.name
  role       = "roles/artifactregistry.writer"
  member     = "serviceAccount:${local.cloud_build_default_service_account}"
}
