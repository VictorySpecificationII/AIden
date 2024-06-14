variable "project" {
  type = string
}

variable "region" {
  type = string
}

variable "database" {
  type = map(any)
}

variable "servers" {
  type = map(any)
}

variable "agents" {
  type = map(any)
}
