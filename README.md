This repo will create a pair of Ubuntu instances on an OpenStack cloud
configured to run docker-compose workloads.

One instance is intended to house
[Clowder](https://github.com/clowder-framework/clowder) and the other a React
front end that uses Clowder as a backend.

To set things up you will need to have the following available:
* A keypair uploaded to OpenStack to allow ssh-ing to the React frontend. You
  will need to add the private key to your ssh agent (ssh agent forwarding is
  also required)
* A network (and router) configured on OpenStack
* An Ubuntu cloud image available on OpenStack (tested with `22.04`)
* 2 fixed IPs on OpenStack (you need to know the actual IP)
* A block storage volume on OpenStack, formatted to ext4 and writable by the
  default user in your OS image
* The IP address(es) you would like to allow to connect to the React frontend
* API access to OpenStack (some helpful info can be found
  [here](https://help.cloud.grnet.gr/t/application-credentials/59) or you can
  contact your cloud admins for help)

Once you have all these requirements you create a Terraform variables file
(e.g., `custom.tfvars`)to store your desired configuration. An example of what
this file looks like is:
```
# Variables
keypair = "admin"   # name of keypair to be used
network = "clowder" # default network to be used

image = "Ubuntu-22.04_220726" # Name of image to be used
default_user = "ubuntu"   # name of default_user in image

ext_ip_clowder = "148.187.148.28"  # external IP address for Clowder
ext_ip_react = "148.187.148.29"  # external IP address for React

ext_ssh_cidrs = ["212.106.235.0/24"] # list of IPs allowed to ssh to react frontend (CIDR notation)

clowder_volume_id = "b4191863-39dd-4031-bb73-4de0e9e491ee"   # ID of volume to store database (formatted to ext4)
```

Once you have you variables defined, you can use
```
terraform apply -var-file=./custom.tfvars
```
