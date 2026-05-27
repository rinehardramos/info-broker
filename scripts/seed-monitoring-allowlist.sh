#!/usr/bin/env bash
# seed-monitoring-allowlist.sh — Phase-2 post-deploy step (Task 6, step 6b).
#
# Seeds the monitoring enforcement allowlist via PUT /v3/monitoring/settings.
# Run this AFTER the Phase-2 images are deployed and the API is healthy.
#
# Usage:
#   ADMIN_TOKEN=<your-admin-jwt> bash scripts/seed-monitoring-allowlist.sh
#   ADMIN_TOKEN=<your-admin-jwt> API_BASE=https://api.infobroker.tech bash scripts/seed-monitoring-allowlist.sh
#
# The allowlist covers:
#   - 172.19.0.1        docker bridge gateway (infobroker compose network)
#   - 127.0.0.1         IPv4 loopback (health-checks, internal calls)
#   - ::1               IPv6 loopback
#   - 172.19.0.0/16     entire docker internal subnet (belt-and-suspenders)
#
# If the docker bridge gateway differs on your host, update the allowlist array
# below (check with: docker network inspect infobroker_default).

set -euo pipefail

API_BASE="${API_BASE:-https://api.infobroker.tech}"
ADMIN_TOKEN="${ADMIN_TOKEN:?ADMIN_TOKEN env var is required}"

echo "Seeding monitoring allowlist at ${API_BASE}/v3/monitoring/settings ..."

curl -fsSL \
  -X PUT \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ${ADMIN_TOKEN}" \
  -d '{
    "enforcement_enabled": true,
    "allowlist": [
      "172.19.0.1",
      "127.0.0.1",
      "::1",
      "172.19.0.0/16"
    ]
  }' \
  "${API_BASE}/v3/monitoring/settings"

echo ""
echo "Allowlist seed complete. Verify with:"
echo "  curl -fsSL -H 'Authorization: Bearer \${ADMIN_TOKEN}' ${API_BASE}/v3/monitoring/settings | python3 -m json.tool"
