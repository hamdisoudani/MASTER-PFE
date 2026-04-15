#!/usr/bin/env bash
# cloudflare-tunnel.sh — expose all three services via Cloudflare Quick Tunnels
# Requires: cloudflared (https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/install-and-setup/installation/)
set -euo pipefail
command -v cloudflared &>/dev/null || { echo "cloudflared not found"; exit 1; }
echo "Starting Cloudflare Quick Tunnels..."
cloudflared tunnel --url http://localhost:8000 &
cloudflared tunnel --url http://localhost:3001 &
cloudflared tunnel --url http://localhost:3000 &
wait
