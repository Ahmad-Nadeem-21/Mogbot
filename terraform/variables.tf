variable "aws_region" {
  description = "AWS region to deploy into. Must be a region where Lightsail is available."
  type        = string
  default     = "us-east-1"
}

variable "availability_zone" {
  description = "Lightsail availability zone (must be in aws_region)."
  type        = string
  default     = "us-east-1a"
}

variable "project_name" {
  description = "Prefix used for all resource names, so multiple deployments (e.g. dev/prod) don't collide."
  type        = string
  default     = "mogbot"
}

variable "lightsail_bundle_id" {
  description = <<-EOT
    Lightsail instance size. This app is a single Flask process with a
    handful of background worker threads - nano is enough for light demo
    traffic. Bump to micro/small if you see memory pressure.
      nano_3_0  = 512MB RAM, 2 vCPU, 20GB SSD  (~$3.50/mo)
      micro_3_0 = 1GB RAM,   2 vCPU, 40GB SSD  (~$5/mo)
      small_3_0 = 2GB RAM,   2 vCPU, 60GB SSD  (~$10/mo)
  EOT
  type        = string
  default     = "micro_3_0"
}

variable "lightsail_blueprint_id" {
  description = "Lightsail OS image."
  type        = string
  default     = "ubuntu_22_04"
}

variable "backend_port" {
  description = "Port gunicorn listens on. Only the CloudFront IP range can reach it directly - see lightsail.tf."
  type        = number
  default     = 8000
}

variable "ssh_allowed_cidrs" {
  description = <<-EOT
    CIDR blocks allowed to SSH into the backend instance (port 22).
    Defaults to open (0.0.0.0/0) so this works out of the box, but you
    should narrow this to your own IP (e.g. "203.0.113.4/32") once you know
    it - check https://checkip.amazonaws.com for your current IP.
  EOT
  type        = list(string)
  default     = ["0.0.0.0/0"]
}
