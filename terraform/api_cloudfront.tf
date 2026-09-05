# CloudFront in front of the Lightsail backend exists purely to get free
# HTTPS (via the default *.cloudfront.net cert) without needing a custom
# domain or running certbot on the box. The frontend is served over HTTPS
# from its own CloudFront distribution (frontend.tf), and browsers block a
# plain-HTTP fetch from an HTTPS page ("mixed content") - so the API needs
# HTTPS too, even though it's really just one small Lightsail instance.
#
# No caching: every request is a live API call (session state changes on
# every POST), so caching would serve stale/wrong responses.
resource "aws_cloudfront_distribution" "api" {
  enabled = true
  comment = "${var.project_name} API (HTTPS in front of Lightsail)"

  origin {
    domain_name = aws_lightsail_static_ip.backend.ip_address
    origin_id   = "mogbot-backend"

    custom_origin_config {
      http_port              = var.backend_port
      https_port             = 443
      origin_protocol_policy = "http-only"
      origin_ssl_protocols   = ["TLSv1.2"]
    }
  }

  default_cache_behavior {
    target_origin_id       = "mogbot-backend"
    viewer_protocol_policy = "redirect-to-https"

    allowed_methods = ["GET", "HEAD", "OPTIONS", "PUT", "POST", "PATCH", "DELETE"]
    cached_methods  = ["GET", "HEAD"]

    # Managed-CachingDisabled: always forward to the origin, never cache.
    cache_policy_id = "4135ea2d-6df8-44a3-9df3-4b5a84be39ad"
    # Managed-AllViewer: forward all headers/cookies/query strings the
    # request actually needs (Content-Type, etc.) - required since the
    # cache policy above doesn't itself forward anything.
    origin_request_policy_id = "216adef6-5c7f-47e4-b989-5492eafa07d3"
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    cloudfront_default_certificate = true
  }

  tags = {
    Project = var.project_name
  }
}
