#!/usr/bin/env bash
# Rsyncs the repo to the Lightsail instance, installs dependencies, prompts
# for ANTHROPIC_API_KEY and writes it directly to the remote .env (never
# touches Terraform state or any local file), and (re)starts the systemd
# service. Run this after `terraform apply` succeeds, from the terraform/
# directory: `./scripts/deploy_backend.sh`
set -euo pipefail

cd "$(dirname "$0")/.."  # now in terraform/
REPO_ROOT="$(cd .. && pwd)"

IP="$(terraform output -raw backend_static_ip)"
PORT="$(terraform output -raw backend_port)"
KEY_FILE="$(mktemp)"
trap 'rm -f "$KEY_FILE"' EXIT

terraform output -raw backend_ssh_private_key > "$KEY_FILE"
chmod 600 "$KEY_FILE"

SSH="ssh -i $KEY_FILE -o StrictHostKeyChecking=accept-new ubuntu@$IP"
RSYNC_SSH="ssh -i $KEY_FILE -o StrictHostKeyChecking=accept-new"

echo "==> Syncing app code to $IP:/opt/mogbot"
rsync -az --delete \
  --exclude='.git' --exclude='.venv' --exclude='__pycache__' --exclude='*.pyc' \
  --exclude='data/' --exclude='terraform/' --exclude='.env' --exclude='.pytest_cache' \
  --exclude='node_modules' \
  -e "$RSYNC_SSH" \
  "$REPO_ROOT/" "ubuntu@$IP:/opt/mogbot/"

echo "==> Installing dependencies on the instance"
$SSH "cd /opt/mogbot && python3 -m venv .venv && .venv/bin/pip install --upgrade pip && .venv/bin/pip install -r requirements.txt"

if $SSH "test -f /opt/mogbot/.env"; then
  echo "==> /opt/mogbot/.env already exists - leaving your ANTHROPIC_API_KEY as-is."
  echo "    Delete it on the instance first if you want to rotate the key here."
else
  echo "==> No .env on the instance yet."
  read -r -s -p "Paste your ANTHROPIC_API_KEY (input hidden): " API_KEY
  echo
  # Piped straight into a remote file - never written to disk on this
  # machine, never passed through Terraform.
  printf 'ANTHROPIC_API_KEY=%s\n' "$API_KEY" | $SSH "cat > /opt/mogbot/.env"
  unset API_KEY
fi

echo "==> Installing systemd service"
sed "s/__BACKEND_PORT__/${PORT}/g" templates/mogbot.service.tpl | $SSH "sudo tee /etc/systemd/system/mogbot.service > /dev/null"
$SSH "sudo systemctl daemon-reload && sudo systemctl enable mogbot && sudo systemctl restart mogbot"

echo "==> Waiting for the service to come up..."
sleep 3
$SSH "sudo systemctl is-active mogbot && curl -sf http://127.0.0.1:${PORT}/health && echo"

API_URL="$(terraform output -raw api_url)"
echo
echo "Backend deployed. Health check via HTTPS (may take ~1 min for CloudFront to propagate):"
echo "  curl ${API_URL}/health"
