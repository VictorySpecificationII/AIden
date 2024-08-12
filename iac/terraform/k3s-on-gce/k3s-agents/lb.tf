resource "google_compute_region_health_check" "k3s-worker-health-check-external" {
  name   = "k3s-worker-external-hc-${var.name}"
  region = var.region

  timeout_sec        = 1
  check_interval_sec = 5

  tcp_health_check {
    port = 443
  }
}

resource "google_compute_region_backend_service" "k3s-worker-server-external" {
  name                  = "k3s-worker-server-external-${var.name}"
  region                = var.region
  load_balancing_scheme = "EXTERNAL"
  health_checks         = [google_compute_region_health_check.k3s-worker-health-check-external.id]
  backend {
    group = google_compute_region_instance_group_manager.k3s-agents.instance_group
  }
}

resource "google_compute_forwarding_rule" "k3s-worker-server-external" {
  name                  = "k3s-worker-server-external-${var.name}"
  region                = var.region
  load_balancing_scheme = "EXTERNAL"
  ip_address            = google_compute_address.k3s-worker-server-external.address
  backend_service       = google_compute_region_backend_service.k3s-worker-server-external.id
  port_range            = "20000-20001"
}
