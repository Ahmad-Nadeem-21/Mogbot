# Generates a fresh SSH key pair for this deployment. The private key is
# only ever held in Terraform state (see README.md's state-security note)
# and in the `terraform output` you save locally - it is never written into
# user_data or any AMI, so it never appears in Lightsail's own instance
# metadata.
resource "aws_lightsail_key_pair" "this" {
  name = "${var.project_name}-key"
}

resource "aws_lightsail_instance" "backend" {
  name              = "${var.project_name}-backend"
  availability_zone = var.availability_zone
  blueprint_id      = var.lightsail_blueprint_id
  bundle_id         = var.lightsail_bundle_id
  key_pair_name     = aws_lightsail_key_pair.this.name
  user_data         = file("${path.module}/user_data.sh.tpl")

  tags = {
    Project = var.project_name
  }
}

resource "aws_lightsail_static_ip" "backend" {
  name = "${var.project_name}-backend-ip"
}

resource "aws_lightsail_static_ip_attachment" "backend" {
  static_ip_name = aws_lightsail_static_ip.backend.name
  instance_name  = aws_lightsail_instance.backend.name
}

# Firewall: SSH open to ssh_allowed_cidrs (narrow this - see variables.tf),
# and the backend port restricted to CloudFront's IP range only via the
# "cloudfront" CIDR alias, so the origin can't be reached directly,
# bypassing rate limiting / HTTPS. See api_cloudfront.tf for the
# distribution that's actually allowed through.
resource "aws_lightsail_instance_public_ports" "backend" {
  instance_name = aws_lightsail_instance.backend.name

  port_info {
    protocol  = "tcp"
    from_port = 22
    to_port   = 22
    cidrs     = var.ssh_allowed_cidrs
  }

  port_info {
    protocol          = "tcp"
    from_port         = var.backend_port
    to_port           = var.backend_port
    cidr_list_aliases = ["cloudfront"]
  }
}
