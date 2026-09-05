#!/bin/bash
# Cloud-init script for the MogBot Lightsail instance.
# Installs system packages only - no app code and no secrets. The app code
# is rsynced in and the systemd service is installed by
# scripts/deploy_backend.sh *after* `terraform apply` finishes; the
# ANTHROPIC_API_KEY is written to .env directly over SSH by that same
# script, so it never passes through this template or Terraform state.
set -euxo pipefail

apt-get update
apt-get install -y python3-venv python3-pip rsync

mkdir -p /opt/mogbot/data
chown -R ubuntu:ubuntu /opt/mogbot
