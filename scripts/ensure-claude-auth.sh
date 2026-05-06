#!/bin/bash
# Extracts Claude Code OAuth token from macOS keychain and sets ANTHROPIC_API_KEY.
# Called automatically before docker compose up via .env generation.
# Falls back to prompting the user if keychain is unavailable.

set -euo pipefail

ENVFILE="${1:-.env}"

# Already set in .env?
if grep -q "^ANTHROPIC_API_KEY=sk-ant-" "$ENVFILE" 2>/dev/null; then
  exit 0
fi

# Try macOS keychain
if command -v security &>/dev/null; then
  CREDS=$(security find-generic-password -s "Claude Code-credentials" -w 2>/dev/null || true)
  if [ -n "$CREDS" ]; then
    TOKEN=$(echo "$CREDS" | python3 -c "import sys,json;print(json.load(sys.stdin)['claudeAiOauth']['accessToken'])" 2>/dev/null || true)
    if [ -n "$TOKEN" ]; then
      # Update or append
      if grep -q "^ANTHROPIC_API_KEY=" "$ENVFILE" 2>/dev/null; then
        sed -i '' "s|^ANTHROPIC_API_KEY=.*|ANTHROPIC_API_KEY=$TOKEN|" "$ENVFILE"
      else
        echo "ANTHROPIC_API_KEY=$TOKEN" >> "$ENVFILE"
      fi
      echo "✓ Claude Code OAuth token extracted from keychain"
      exit 0
    fi
  fi
fi

# No keychain — check if already set via env
if [ -n "${ANTHROPIC_API_KEY:-}" ]; then
  exit 0
fi

echo "⚠ Claude Code not authenticated."
echo "  Run: claude auth login"
echo "  Then re-run this script or docker compose up"
exit 1
