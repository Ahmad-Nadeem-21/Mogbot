output "backend_port" {
  description = "Port gunicorn listens on (used by deploy scripts)."
  value       = var.backend_port
}

output "backend_static_ip" {
  description = "Lightsail static IP - use this to SSH in (scripts/deploy_backend.sh does this for you)."
  value       = aws_lightsail_static_ip.backend.ip_address
}

output "backend_ssh_username" {
  value = "ubuntu"
}

output "backend_ssh_private_key" {
  description = "Save this to a file (e.g. mogbot-key.pem), chmod 600 it, and use it to SSH into the backend instance. Also used automatically by scripts/deploy_backend.sh."
  value       = aws_lightsail_key_pair.this.private_key
  sensitive   = true
}

output "api_url" {
  description = "HTTPS URL for the backend API (CloudFront in front of Lightsail). Put this in web/index.html's <meta name=\"mogbot-api-base\"> - scripts/deploy_frontend.sh does this for you."
  value       = "https://${aws_cloudfront_distribution.api.domain_name}"
}

output "frontend_url" {
  description = "HTTPS URL for the deployed static frontend."
  value       = "https://${aws_cloudfront_distribution.frontend.domain_name}"
}

output "frontend_s3_bucket" {
  description = "S3 bucket the frontend files live in (used by scripts/deploy_frontend.sh)."
  value       = aws_s3_bucket.frontend.bucket
}

output "frontend_cloudfront_distribution_id" {
  description = "Needed to invalidate the CloudFront cache after a frontend deploy."
  value       = aws_cloudfront_distribution.frontend.id
}
