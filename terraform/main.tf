terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "5.24.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
  zone    = var.zone
}

resource "google_compute_network" "vpc_network" {
  name = "aiden"
}

resource "google_compute_firewall" "k3s-firewall" {
  name = "k3s-firewall"
  #network = "default"
  network = google_compute_network.vpc_network.name
  allow {
    protocol = "tcp"
    ports    = ["6443", "22"]
  }
  target_tags = ["k3s"]
}

resource "google_compute_instance" "k3s_master_instance" {
  name         = "k3s-master"
  machine_type = "e2-micro"
  tags         = ["k3s", "k3s-master"]

  boot_disk {
    initialize_params {
      image = "debian-cloud/debian-11"
    }
  }

  network_interface {
    network = "default"

    access_config {}
  }

  provisioner "local-exec" {
    command = "k3sup install --ip ${self.network_interface[0].access_config[0].nat_ip} --context k3s --ssh-key ~/.ssh/google_compute_engine --user $(whoami)"
  }

  depends_on = [
    google_compute_firewall.k3s-firewall, google_compute_network.vpc_network
  ]
}

resource "google_compute_instance" "k3s_worker_instance" {
  count        = 3
  name         = "k3s-worker-${count.index}"
  machine_type = "e2-micro"
  tags         = ["k3s", "k3s-worker"]

  boot_disk {
    initialize_params {
      image = "debian-cloud/debian-11"
    }
  }

  network_interface {
    #network = "default"
    network = google_compute_network.vpc_network.name

    access_config {}
  }

  provisioner "local-exec" {
    command = "k3sup join --ip ${self.network_interface[0].access_config[0].nat_ip} --server-ip ${google_compute_instance.k3s_master_instance.network_interface[0].access_config[0].nat_ip} --ssh-key ~/.ssh/google_compute_engine --user $(whoami)"
  }

  depends_on = [
    google_compute_firewall.k3s-firewall, google_compute_network.vpc_network
  ]
}
