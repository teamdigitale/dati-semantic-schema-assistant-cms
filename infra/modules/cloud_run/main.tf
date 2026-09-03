locals {
  agent_name     = "${var.service_prefix}-agent-${var.environment}"
  web_name       = "${var.service_prefix}-web-${var.environment}"
  ingestion_name = "${var.service_prefix}-ingestion-${var.environment}"
}

resource "google_cloud_run_v2_service" "web" {
  project              = var.project_id
  name                 = local.web_name
  location             = var.region
  ingress              = "INGRESS_TRAFFIC_ALL"
  invoker_iam_disabled = false
  deletion_protection  = var.deletion_protection
  labels               = var.labels

  template {
    service_account                  = var.web_service_account_email
    timeout                          = "60s"
    max_instance_request_concurrency = 80

    scaling {
      min_instance_count = 0
      max_instance_count = 3
    }

    containers {
      image = var.web_image

      ports {
        container_port = 8080
      }

      env {
        name  = "APP_ENV"
        value = var.environment
      }

      env {
        name  = "AGENT_SERVICE_URL"
        value = google_cloud_run_v2_service.agent.uri
      }

      env {
        name  = "FRAME_ANCESTORS"
        value = join(",", var.web_frame_ancestors)
      }

      resources {
        limits = {
          cpu    = "1"
          memory = "512Mi"
        }

        cpu_idle = true
      }
    }
  }

  traffic {
    type    = "TRAFFIC_TARGET_ALLOCATION_TYPE_LATEST"
    percent = 100
  }

  lifecycle {
    # Application images are deployed outside Terraform. gcloud also records
    # its client metadata, which must not create infrastructure drift.
    ignore_changes = [
      client,
      client_version,
      template[0].containers[0].image,
    ]
  }
}

resource "google_cloud_run_v2_service" "agent" {
  project              = var.project_id
  name                 = local.agent_name
  location             = var.region
  ingress              = "INGRESS_TRAFFIC_ALL"
  invoker_iam_disabled = false
  deletion_protection  = var.deletion_protection
  labels               = var.labels

  template {
    service_account                  = var.agent_service_account_email
    timeout                          = "60s"
    max_instance_request_concurrency = 10

    scaling {
      min_instance_count = 0
      max_instance_count = 3
    }

    containers {
      image = var.agent_image

      ports {
        container_port = 8080
      }

      env {
        name  = "APP_ENV"
        value = var.environment
      }

      env {
        name  = "GOOGLE_CLOUD_PROJECT"
        value = var.project_id
      }

      env {
        name  = "GOOGLE_CLOUD_LOCATION"
        value = var.region
      }

      env {
        name  = "FIRESTORE_DATABASE"
        value = var.firestore_database_name
      }

      env {
        name  = "SCHEMA_ASSISTANT_BUCKET"
        value = var.bucket_name
      }

      env {
        name  = "LOG_LEVEL"
        value = "INFO"
      }

      env {
        name  = "CHAT_MODEL"
        value = "gemini-2.5-flash"
      }

      env {
        name  = "EMBEDDING_MODEL"
        value = "gemini-embedding-001"
      }

      env {
        name  = "EMBEDDING_DIMENSION"
        value = "2048"
      }

      env {
        name  = "FIRESTORE_CHUNKS_COLLECTION_GROUP"
        value = "chunks"
      }

      env {
        name  = "LLM_ENABLED"
        value = "true"
      }

      env {
        name  = "RAG_ENABLED"
        value = "true"
      }

      env {
        name  = "RAG_TOP_K"
        value = "10"
      }

      env {
        name  = "RAG_CONTEXT_MAX_CHARS"
        value = "14000"
      }

      env {
        name  = "RAG_MAX_DISTANCE"
        value = "0.45"
      }

      env {
        name  = "RESOURCES_CONFIG_PATH"
        value = "config/resources.json"
      }

      env {
        name  = "COST_STATUS"
        value = "green"
      }

      env {
        name  = "MAX_INPUT_CHARS"
        value = "4000"
      }

      env {
        name  = "MAX_HISTORY_MESSAGES"
        value = "12"
      }

      env {
        name  = "MAX_HISTORY_MESSAGE_CHARS"
        value = "2000"
      }

      env {
        name  = "MAX_OUTPUT_TOKENS"
        value = "2048"
      }

      env {
        name  = "THINKING_BUDGET"
        value = "512"
      }

      resources {
        limits = {
          cpu    = "1"
          memory = "1Gi"
        }

        cpu_idle = true
      }
    }
  }

  traffic {
    type    = "TRAFFIC_TARGET_ALLOCATION_TYPE_LATEST"
    percent = 100
  }

  lifecycle {
    # Application images are deployed outside Terraform. gcloud also records
    # its client metadata, which must not create infrastructure drift.
    ignore_changes = [
      client,
      client_version,
      template[0].containers[0].image,
    ]
  }
}

# The service is reachable from the internet, but IAM keeps it private.
resource "google_cloud_run_v2_service_iam_binding" "agent_invokers" {
  project  = var.project_id
  location = google_cloud_run_v2_service.agent.location
  name     = google_cloud_run_v2_service.agent.name
  role     = "roles/run.invoker"
  members = concat(
    var.developer_invokers,
    ["serviceAccount:${var.web_service_account_email}"],
  )
}

resource "google_cloud_run_v2_service_iam_binding" "web_public_invokers" {
  project  = var.project_id
  location = google_cloud_run_v2_service.web.location
  name     = google_cloud_run_v2_service.web.name
  role     = "roles/run.invoker"
  members  = ["allUsers"]
}

resource "google_cloud_run_v2_job" "ingestion" {
  project             = var.project_id
  name                = local.ingestion_name
  location            = var.region
  deletion_protection = var.deletion_protection
  labels              = var.labels

  template {
    task_count  = 1
    parallelism = 1

    template {
      service_account = var.ingestion_service_account_email
      max_retries     = 0
      timeout         = "3600s"

      containers {
        image = var.ingestion_image

        env {
          name  = "APP_ENV"
          value = var.environment
        }

        env {
          name  = "GOOGLE_CLOUD_PROJECT"
          value = var.project_id
        }

        env {
          name  = "GOOGLE_CLOUD_LOCATION"
          value = var.region
        }

        env {
          name  = "FIRESTORE_DATABASE"
          value = var.firestore_database_name
        }

        env {
          name  = "SCHEMA_ASSISTANT_BUCKET"
          value = var.bucket_name
        }

        env {
          name  = "EMBEDDING_MODEL"
          value = "gemini-embedding-001"
        }

        env {
          name  = "EMBEDDING_DIMENSION"
          value = "2048"
        }

        env {
          name  = "FIRESTORE_CHUNKS_COLLECTION_GROUP"
          value = "chunks"
        }

        env {
          name  = "ENTITIES_CONFIG_PATH"
          value = "config/entities_config.json"
        }

        env {
          name  = "INGESTION_GCS_DOCS_PREFIX"
          value = "incoming/docs"
        }

        env {
          name  = "INGESTION_MAX_CHUNK_CHARS"
          value = "3500"
        }

        env {
          name  = "INGESTION_CHUNK_OVERLAP_CHARS"
          value = "300"
        }

        env {
          name  = "INGESTION_MAX_TRIPLES_PER_FILE"
          value = "600"
        }

        env {
          name  = "INGESTION_FIRESTORE_WRITE_BATCH_SIZE"
          value = "50"
        }

        env {
          name  = "INGESTION_DRY_RUN"
          value = "false"
        }

        resources {
          limits = {
            cpu    = "2"
            memory = "4Gi"
          }
        }
      }
    }
  }

  lifecycle {
    # Terraform owns the job shape; application deploys own the image. Ignore
    # gcloud client metadata for the same reason as the services above.
    ignore_changes = [
      client,
      client_version,
      template[0].template[0].containers[0].image,
    ]
  }
}

resource "google_cloud_run_v2_job_iam_binding" "ingestion_invokers" {
  project  = var.project_id
  location = google_cloud_run_v2_job.ingestion.location
  name     = google_cloud_run_v2_job.ingestion.name
  role     = "roles/run.invoker"
  members  = var.developer_invokers
}

# roles/run.developer lets the developer use the console to inspect, run, and stop executions.
resource "google_cloud_run_v2_job_iam_binding" "ingestion_developers" {
  project  = var.project_id
  location = google_cloud_run_v2_job.ingestion.location
  name     = google_cloud_run_v2_job.ingestion.name
  role     = "roles/run.developer"
  members  = var.developer_invokers
}
