#!/usr/bin/env bash
# Points web/index.html at the deployed API, syncs web/ to the frontend S3
# bucket, and invalidates the CloudFront cache. Run after
# deploy_backend.sh, from the terraform/ directory: `./scripts/deploy_frontend.sh`
set -euo pipefail

cd "$(dirname "$0")/.."  # now in terraform/
REPO_ROOT="$(cd .. && pwd)"

API_URL="$(terraform output -raw api_url)"
BUCKET="$(terraform output -raw frontend_s3_bucket)"
DISTRIBUTION_ID="$(terraform output -raw frontend_cloudfront_distribution_id)"

BUILD_DIR="$(mktemp -d)"
trap 'rm -rf "$BUILD_DIR"' EXIT

cp -r "$REPO_ROOT/web/." "$BUILD_DIR/"

# Point the frontend at the deployed API. This is a build-time edit of a
# throwaway copy - your working tree's web/index.html is untouched.
sed -i.bak "s#<meta name=\"mogbot-api-base\" content=\"[^\"]*\">#<meta name=\"mogbot-api-base\" content=\"${API_URL}\">#" "$BUILD_DIR/index.html"
rm -f "$BUILD_DIR/index.html.bak"

echo "==> Syncing $BUILD_DIR to s3://$BUCKET"
aws s3 sync "$BUILD_DIR" "s3://$BUCKET" --delete

echo "==> Invalidating CloudFront cache ($DISTRIBUTION_ID)"
aws cloudfront create-invalidation --distribution-id "$DISTRIBUTION_ID" --paths "/*" > /dev/null

FRONTEND_URL="$(terraform output -raw frontend_url)"
echo
echo "Frontend deployed (API base: ${API_URL}):"
echo "  ${FRONTEND_URL}"
echo "(CloudFront invalidation can take a minute or two to finish propagating.)"
