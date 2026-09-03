resource "google_project_service" "enabled" {
  for_each = var.services

  project = var.project_id
  service = each.value

  disable_dependent_services = false
  disable_on_destroy         = false
}
