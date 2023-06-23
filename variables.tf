# Variables
variable "keypair" {
  type    = string
  default = "admin"
  description = "*Name* of the ssh key (on cloud provider) to be used"
  nullable = false
}

variable "network" {
  type    = string
  default = "clowder" 
  description = "*Name* of the network (on cloud provider) to attach to"
  nullable = false
}

variable "ext_ssh_cidrs" {
  type    = list(string)
  description = "List of address pools allowed to ssh to React frontend (CIDR notation)"
  nullable = false
}

variable "image" {
  type    = string
  description = "*Name* of the Ubuntu OS image (on cloud provider) to attach to"
  nullable = false
}

variable "default_user" {
  type    = string
  description = "Username of default user in requested OS image"
  nullable = false
}

variable "ext_ip_clowder" {
  type    = string
  description = "Fixed IP (from cloud provider) to attach to Clowder instance"
  nullable = false
}

variable "ext_ip_react" {
  type    = string
  description = "Fixed IP (from cloud provider) to attach to React instance"
  nullable = false
}

variable "clowder_volume_id" {
  type    = string
  sensitive = true
  description = "*ID* (on cloud provider) of volume to store Clowder database and settings (must be ext4 formatted)"
  nullable = false
}

variable "domain" {
  type    = string
  sensitive = true
  description = "Cloudflare managed TLD to associate clowder with for https"
  nullable = false
}
