#!/usr/bin/env bash
# Deploy the info-broker frontend to Cloudflare Pages.
#
# Two modes:
#   1. First-time setup: creates the Pages project + does the initial deploy.
#      Requires `wrangler login` to have been done in this shell.
#   2. Subsequent deploys: builds + uploads dist/ to the existing project.
#
# Usage:
#   ./bin/cloudflare-pages-deploy.sh                   # build + deploy preview
#   ./bin/cloudflare-pages-deploy.sh --production      # deploy as production
#   ./bin/cloudflare-pages-deploy.sh --create          # one-time project setup

set -euo pipefail

cd "$(dirname "$0")/../frontend"

PROD=0
CREATE=0
for arg in "$@"; do
  case "$arg" in
    --production) PROD=1 ;;
    --create)     CREATE=1 ;;
    -h|--help)
      sed -n '2,15p' "$0"; exit 0 ;;
    *) echo "Unknown arg: $arg"; exit 1 ;;
  esac
done

# Wrangler is local to frontend/. Use pnpm exec so we don't rely on global install.
WRANGLER="pnpm exec wrangler"

# Auth check
if ! $WRANGLER whoami 2>&1 | grep -qE "logged in|email"; then
  echo "✗ Not authenticated. Run inside frontend/:"
  echo "    pnpm exec wrangler login"
  exit 1
fi

# Optional one-time project creation
if [[ $CREATE -eq 1 ]]; then
  echo "▶ Creating Cloudflare Pages project 'info-broker'…"
  $WRANGLER pages project create info-broker \
    --production-branch=main \
    --compatibility-date=2026-05-20 || {
      echo "(if 'project already exists', that's fine — continuing)"
    }
fi

# Build
echo "▶ Building production bundle (VITE_API_URL=https://api.infobroker.net)…"
VITE_API_URL=https://api.infobroker.net pnpm build

# Deploy
if [[ $PROD -eq 1 ]]; then
  echo "▶ Deploying to PRODUCTION (main branch)…"
  $WRANGLER pages deploy dist --project-name=info-broker --branch=main
else
  echo "▶ Deploying as preview…"
  $WRANGLER pages deploy dist --project-name=info-broker
fi
