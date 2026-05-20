#!/usr/bin/env bash
# Cloudflare Tunnel scripted setup, after `cloudflared tunnel login` is done.
#
# Creates the tunnel, routes api.infobroker.net DNS to it, and writes the
# connector token into .env for the docker-compose `cloudflared` service.

set -euo pipefail

TUNNEL_NAME="${TUNNEL_NAME:-info-broker}"
ZONE="${ZONE:-infobroker.net}"
API_SUB="${API_SUB:-api.${ZONE}}"
MCP_SUB="${MCP_SUB:-mcp.${ZONE}}"

export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"

if [[ ! -f "$HOME/.cloudflared/cert.pem" ]]; then
  echo "✗ ~/.cloudflared/cert.pem missing. Run \`cloudflared tunnel login\` first."
  exit 1
fi

echo "▶ Creating tunnel: ${TUNNEL_NAME}"
if cloudflared tunnel list 2>&1 | grep -qE "\b${TUNNEL_NAME}\b"; then
  echo "  (already exists, reusing)"
else
  cloudflared tunnel create "${TUNNEL_NAME}"
fi

# Extract UUID
TUNNEL_UUID=$(cloudflared tunnel list 2>&1 | awk -v n="${TUNNEL_NAME}" '$2 == n {print $1}' | head -1)
if [[ -z "$TUNNEL_UUID" ]]; then
  echo "✗ couldn't determine tunnel UUID"; exit 1
fi
echo "  UUID: ${TUNNEL_UUID}"

echo "▶ Routing DNS: ${API_SUB} → tunnel"
cloudflared tunnel route dns "${TUNNEL_NAME}" "${API_SUB}" 2>&1 | tail -3 || true

echo "▶ Routing DNS: ${MCP_SUB} → tunnel"
cloudflared tunnel route dns "${TUNNEL_NAME}" "${MCP_SUB}" 2>&1 | tail -3 || true

echo "▶ Reading connector token"
TOKEN=$(cloudflared tunnel token "${TUNNEL_NAME}")
if [[ -z "$TOKEN" ]]; then echo "✗ no token returned"; exit 1; fi
echo "  token length: ${#TOKEN} chars"

# Write to .env (idempotent)
ENV_FILE=".env"
if [[ -f "$ENV_FILE" ]] && grep -q '^CLOUDFLARED_TOKEN=' "$ENV_FILE"; then
  # update in place
  sed -i.bak "s|^CLOUDFLARED_TOKEN=.*|CLOUDFLARED_TOKEN=${TOKEN}|" "$ENV_FILE"
  rm -f "$ENV_FILE.bak"
  echo "▶ Updated CLOUDFLARED_TOKEN in $ENV_FILE"
else
  echo "CLOUDFLARED_TOKEN=${TOKEN}" >> "$ENV_FILE"
  echo "▶ Appended CLOUDFLARED_TOKEN to $ENV_FILE"
fi

# Public hostname → service mapping must be configured in the dashboard
# or via a config file. We provide a config file approach since it's easier
# to version and reproduce.
mkdir -p "$HOME/.cloudflared"
cat > "$HOME/.cloudflared/config.yml" << EOF
tunnel: ${TUNNEL_UUID}
credentials-file: ${HOME}/.cloudflared/${TUNNEL_UUID}.json

ingress:
  - hostname: ${API_SUB}
    service: http://info-broker-api:8000
  - hostname: ${MCP_SUB}
    service: http://info-broker-api:8000
  - service: http_status:404
EOF
echo "▶ Wrote ${HOME}/.cloudflared/config.yml"

echo ""
echo "${GREEN:-}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET:-}"
echo "  ✓ Tunnel ready. Next:"
echo ""
echo "    docker compose --profile tunnel up -d cloudflared"
echo "    docker compose logs --tail 20 cloudflared"
echo ""
echo "  Verify:"
echo "    curl -fsS https://${API_SUB}/healthz"
