# Configure the OpenStack Provider
terraform {
  required_providers {
    openstack = {
      source = "terraform-provider-openstack/openstack"
    }
    cloudflare = {
      source = "cloudflare/cloudflare"
      version = "~> 4"
    }
  }
}

# Security Groups
## Internal ssh
resource "openstack_compute_secgroup_v2" "secgroup_int_ssh" {
  depends_on = [openstack_compute_instance_v2.react]
  name        = "clowder_secgroup_int_ssh"
  description = "my ssh security group"

  rule {
    from_port   = 22
    to_port     = 22
    ip_protocol = "tcp"
    cidr        = "${openstack_compute_instance_v2.react.access_ip_v4}/32"
  }
}
## External ssh (only used for react front end)
resource "openstack_compute_secgroup_v2" "secgroup_ext_ssh" {
  name        = "react_secgroup_ext_ssh"
  description = "my ssh security group"

  # Dynamic block to allow for multiple ranges
  dynamic "rule" {
    for_each = var.ext_ssh_cidrs
    content {
      from_port   = 22
      to_port     = 22
      ip_protocol = "tcp"
      cidr        = rule.value
    }
  }
}
## HTTP access
resource "openstack_compute_secgroup_v2" "secgroup_www" {
  name        = "clowder_secgroup_www"
  description = "my www security group"
  rule {
    from_port   = 80
    to_port     = 80
    ip_protocol = "tcp"
    cidr        = "0.0.0.0/0"
  }

  rule {
    from_port   = 443
    to_port     = 443
    ip_protocol = "tcp"
    cidr        = "0.0.0.0/0"
  }
}

# Data sources
## Get Image ID
data "openstack_images_image_v2" "image" {
  name        = var.image
  most_recent = true
}
## Get Clowder flavor id
data "openstack_compute_flavor_v2" "clowder_flavor" {
  name = "m1.x-large" # flavor to be used
}
## Get react flavor id
data "openstack_compute_flavor_v2" "react_flavor" {
  name = "m1.medium" # flavor to be used
}

# Create instances

## Create clowder instance
resource "openstack_compute_instance_v2" "clowder" {
  name            = "ClowderBackend"  #Instance name
  image_id        = data.openstack_images_image_v2.image.id
  flavor_id       = data.openstack_compute_flavor_v2.clowder_flavor.id
  key_pair        = var.keypair
  security_groups = [
    "${openstack_compute_secgroup_v2.secgroup_int_ssh.name}",
    "${openstack_compute_secgroup_v2.secgroup_www.name}"
  ]

  network {
    name = var.network
  }
}
### Add Floating ip
resource "openstack_compute_floatingip_associate_v2" "fip_clowder" {
  floating_ip = var.ext_ip_clowder
  instance_id = openstack_compute_instance_v2.clowder.id
}
### Attach storage
resource "openstack_compute_volume_attach_v2" "va_1" {
  instance_id = "${openstack_compute_instance_v2.clowder.id}"
  volume_id   = "${var.clowder_volume_id}"
}

## Create React frontend instance
resource "openstack_compute_instance_v2" "react" {
  name            = "ReactFrontend"  #Instance name
  image_id        = data.openstack_images_image_v2.image.id
  flavor_id       = data.openstack_compute_flavor_v2.react_flavor.id
  key_pair        = var.keypair
  security_groups = [
    "${openstack_compute_secgroup_v2.secgroup_ext_ssh.name}",
    "${openstack_compute_secgroup_v2.secgroup_www.name}"
  ]

  network {
    name = var.network
  }
}
### Add Floating ip
resource "openstack_compute_floatingip_associate_v2" "fip_react" {
  floating_ip = var.ext_ip_react
  instance_id = openstack_compute_instance_v2.react.id
}

# Create locals to handle our various installation needs
locals {
  update_inline = [
    # Update
    "set -o errexit",
    "sudo apt update",
    "sudo DEBIAN_FRONTEND=noninteractive NEEDRESTART_MODE=a apt upgrade -y"
  ]
  # Install docker and docker-compose
  docker_inline = [
    "curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg",
    "echo deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable > docker.list",
    "sudo mv docker.list /etc/apt/sources.list.d/docker.list",
    "sudo apt update",
    "sudo DEBIAN_FRONTEND=noninteractive NEEDRESTART_MODE=a apt install -y docker-ce",
    "sudo DEBIAN_FRONTEND=noninteractive NEEDRESTART_MODE=a apt upgrade -y",
    "sudo usermod -aG docker ${var.default_user}",
    "mkdir -p ~/.docker/cli-plugins/",
    "curl -SL https://github.com/docker/compose/releases/download/v2.7.0/docker-compose-linux-x86_64 -o ~/.docker/cli-plugins/docker-compose",
    "chmod +x ~/.docker/cli-plugins/docker-compose"
  ]
  # Add an editor and git
  devel_inline = [
    "sudo DEBIAN_FRONTEND=noninteractive NEEDRESTART_MODE=a apt install -y vim git rsync"
  ]
  # Reboot to restart services and mount volume
  reboot_inline = [
      "sudo shutdown -r +1"
  ]
  # Mount the disk by default (1st partition, Clowder VM only)
  mount_inline = [
    "sudo su -c 'echo ${openstack_compute_volume_attach_v2.va_1.device}1 /clowder ext4 defaults 0 2 >> /etc/fstab'"
  ]
}

# Create and copy Clowder configuration file over to react frontend
resource "null_resource" "provision_file_clowder" {
  depends_on = [openstack_compute_instance_v2.react, openstack_compute_floatingip_associate_v2.fip_react]
  provisioner "file" {
    connection {
      agent       = true  # Use the agent to pass on the key
      timeout     = "10m"
      host        = "${openstack_compute_floatingip_associate_v2.fip_react.floating_ip}"
      user        = "ubuntu"
    }
    content =  join("\n", concat(
      local.update_inline,
      local.docker_inline,
      local.devel_inline,
      local.mount_inline,
      local.reboot_inline
    ))
    destination = "clowder_provision.sh"
  }
}

# Create and copy react configuration file over to react frontend
resource "null_resource" "provision_file_react" {
  depends_on = [openstack_compute_instance_v2.react, openstack_compute_floatingip_associate_v2.fip_react]
  provisioner "file" {
    connection {
      agent       = true  # Use the agent to pass on the key
      timeout     = "10m"
      host        = "${openstack_compute_floatingip_associate_v2.fip_react.floating_ip}"
      user        = "ubuntu"
    }
    content =  join("\n", concat(
      local.update_inline,
      local.docker_inline,
      local.devel_inline,
      local.reboot_inline
    ))
    destination = "react_provision.sh"
  }
}

# Configure things for react (and Clowder)
resource "null_resource" "remote-exec-react" {
  depends_on = [
    null_resource.provision_file_react,
    null_resource.provision_file_clowder,
    openstack_compute_instance_v2.clowder
  ]
  provisioner "remote-exec" {
    connection {
      agent       = true  # Use the agent to pass on the key
      timeout     = "10m"
      host        = "${openstack_compute_floatingip_associate_v2.fip_react.floating_ip}"
      user        = "ubuntu"
    }

    inline = [
      "set -o errexit",
      # Give a shortcut to clowder VM
      "sudo su -c 'echo ${openstack_compute_instance_v2.clowder.access_ip_v4} clowder >> /etc/hosts'",
      # Send the provisioning files to Clowder
      "scp -o StrictHostKeyChecking=accept-new clowder_provision.sh clowder:",
      # Now do clowder basic provisioning
      "ssh clowder 'bash clowder_provision.sh'",
      # Finally do own provisioning
      "bash react_provision.sh"
    ]
  }
}

# Configure Cloudflare
data "cloudflare_zones" "domain" {
  filter {
    name   = var.domain
    status = "active"
    paused = false
  }
}

resource "cloudflare_record" "clowder" {
  zone_id = data.cloudflare_zones.domain.zones[0].id
  name    = "clowder"
  value   = openstack_compute_floatingip_associate_v2.fip_clowder.floating_ip
  type    = "A"
  proxied = true
}

# Output VM IP Addresses
output "clowder_private_ip" {
 value = openstack_compute_instance_v2.clowder.access_ip_v4
}
output "clowder_floating_ip" {
 value = openstack_compute_floatingip_associate_v2.fip_clowder.floating_ip
}
output "react_private_ip" {
 value = openstack_compute_instance_v2.react.access_ip_v4
}
output "react_floating_ip" {
 value = openstack_compute_floatingip_associate_v2.fip_react.floating_ip
}
output "default_user" {
 value = var.default_user
}
