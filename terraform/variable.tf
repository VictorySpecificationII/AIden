# variable.tf are files where all variables are declared; these might or might not have a default value

variable "project_id" {
  type        = string
  default     = "none"
  description = "GCP Project ID"
}

variable "region" {
  type        = string
  default     = "none"
  description = "GCP Region"
}

variable "zone" {
  type        = string
  default     = "none"
  description = "GCP Zone"
}
