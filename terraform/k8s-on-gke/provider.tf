# https://registry.terraform.io/providers/hashicorp/google/latest/docs
provider "google" {
  project = "aiden-ai-copilot"
  region  = "europe-west4"
}

# https://www.terraform.io/language/settings/backends/gcs
terraform {
  backend "local" {

  }
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 4.0"
    }
  }
}