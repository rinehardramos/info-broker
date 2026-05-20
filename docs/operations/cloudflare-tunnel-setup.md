# Cloudflare Tunnel — `api.infobroker.net` → local FastAPI

End-to-end: turn the home Docker stack into a tunneled origin for the
Cloudflare Pages frontend, so requests to `api.infobroker.net` reach
`http://info-broker-api:8000` over an outbound-only mTLS tunnel.

## Why this is not fully Playwright-driven

`wrangler login` works under Playwright because its OAuth callback is direct.
`cloudflared tunnel login` goes through `dash.cloudflare.com/argotunnel`
which is gated by Cloudflare's Turnstile bot challenge — Turnstile
fingerprints automation browsers and refuses Playwright. So this one step is
manual; everything after it is scripted.

## Step 1 — issue a tunnel certificate (manual, ~30s)

In your own terminal (NOT Playwright):

```bash
brew install cloudflared          # if not already done
cloudflared tunnel login
```

Your default browser opens to `dash.cloudflare.com/argotunnel`. Cloudflare
sees your existing dashboard session, no Turnstile challenge fires. Pick the
`infobroker.net` zone, click **Authorize**.

cloudflared writes `~/.cloudflared/cert.pem`. The rest of the setup uses
this cert and no further browser interaction.

## Step 2 — create the named tunnel (scripted)

```bash
./bin/cloudflare-tunnel-setup.sh
```

What that script does (all via cloudflared CLI):

1. `cloudflared tunnel create info-broker` — provisions a tunnel, gets a UUID.
2. Writes the tunnel credentials JSON to `~/.cloudflared/<uuid>.json`.
3. `cloudflared tunnel route dns info-broker api.infobroker.net` — creates a
   CNAME from `api` → `<uuid>.cfargotunnel.com`. Survives without your laptop online.
4. Reads the connector token via `cloudflared tunnel token <name>` and writes
   it into `.env` as `CLOUDFLARED_TOKEN=<token>`.

## Step 3 — start the tunnel container (scripted)

```bash
docker compose --profile tunnel up -d cloudflared
docker compose logs --tail 20 cloudflared
```

Look for `Registered tunnel connection` in the logs (usually within 5s).
At that point `api.infobroker.net` resolves at the Cloudflare edge and
proxies to your local FastAPI.

## Step 4 — verify end-to-end (scripted)

```bash
curl -fsS https://api.infobroker.net/healthz
# → {"status":"ok"} from local FastAPI

# Verify via the Pages frontend
pnpm --prefix frontend playwright test e2e/verify-pages-live.spec.ts
# Now the auth/providers fetch should succeed (was ERR_CONNECTION_REFUSED before)
```

## Configuration files

- `cloudflared` service is already in `docker-compose.yml` under `--profile tunnel`.
- Ingress mapping is configured at the **dashboard side** (Zero Trust → Tunnels →
  info-broker → Public Hostnames):
  | Hostname | Service | Path |
  |---|---|---|
  | `api.infobroker.net` | `http://info-broker-api:8000` | / |
  | `mcp.infobroker.net` | `http://info-broker-api:8000` | /mcp |
  | `temporal.infobroker.net` | `http://temporal-ui:8080` | / (Access-gated) |
- CORS allow-list updated in `app/main.py:289` to include
  `https://info-broker.pages.dev`, `https://infobroker.net`,
  `https://www.infobroker.net`, and a regex for preview deploys
  (`*.info-broker.pages.dev`).

## Rollback

- Stop tunnel: `docker compose stop cloudflared`. The api subdomain returns
  502 from Cloudflare edge but does not break the frontend (which already
  handles `ERR_CONNECTION_REFUSED` via `InlineError` retry).
- Remove tunnel entirely: `cloudflared tunnel delete info-broker`.
- Revoke cert: delete `~/.cloudflared/cert.pem` and the corresponding zone-level
  token at Cloudflare → My Profile → API Tokens.

## Cost

$0. Tunnels and DNS are free.
