# Backend deploy runbook

> **Why this exists:** "Merge to main" deploys the **frontend only** (via
> `.github/workflows/cloudflare-pages.yml` → Cloudflare Pages). The backend
> at `api.infobroker.tech` runs as a Docker container on the **home
> server** behind Cloudflare Tunnel and has **no automated deploy**.
> Forgetting this step makes new API routes 404 in prod even after a green
> merge.

## Architecture recap

```
Browser
   │
   ▼
infobroker.tech                       (Cloudflare Pages — auto-deploys on main)
   │  fetches /v3/* from
   ▼
api.infobroker.tech                   (Cloudflare DNS → tunnel)
   │
   ▼
cloudflared on HOME SERVER            (separate machine; not your laptop)
   │
   ▼
info-broker-api:8000 (Docker)         (built from `.` — image not mounted source)
```

The home server is the **only** machine whose `info-broker-api` container
serves prod traffic. Rebuilding the container on any other machine has no
effect on `api.infobroker.tech`.

## When you need to deploy the backend

Any PR that touches:
- Anything under `app/` (Python source)
- `pyproject.toml` / `uv.lock` (Python deps)
- The `Dockerfile`
- `docker-compose.yml` (the API service block)

If a PR is **frontend-only** (`frontend/**` only), skip this — the
Cloudflare Pages deploy is enough.

## Deploy procedure

On the **home server** (NOT your laptop), as the user that owns the docker
compose stack:

```bash
cd /path/to/info-broker          # wherever it's cloned on the server
git pull origin main
docker compose build info-broker-api
docker compose up -d info-broker-api
```

Optional but recommended for a slightly less brittle build:

```bash
docker compose build --pull info-broker-api   # refreshes base image too
```

Expected duration:
- **Fast path (layer cache hit):** ~30s
- **Cold path (deps changed):** 2–5 min while `uv sync` runs

During the restart there's a ~5–10s window where `api.infobroker.tech`
returns 502/503. The Cloudflare Health Check (per
[hybrid-architecture.md](./hybrid-architecture.md#observability)) will not
alert at that latency.

## Verification

Run **from any machine** (laptop is fine — verifies via the tunnel, which
is what matters):

```bash
# Should return 401 (route exists, needs auth) — NOT 404
curl -s -o /dev/null -w '%{http_code}\n' https://api.infobroker.tech/<new-route>

# Diff route counts: should match localhost on the home server
curl -s https://api.infobroker.tech/openapi.json | jq '.paths | length'
```

If the OpenAPI total didn't grow after a release that added routes, the
home-server container is still on the old image — re-run the deploy
procedure.

## Failure mode: "new route 404s in prod after merge"

Symptom: a route added in a merged PR returns 404 at
`api.infobroker.tech/<route>` even though it returns 200/401 at
`http://localhost:8000/<route>` on the home server.

Causes, in likelihood order:

1. **Backend not deployed.** Most common. Run the deploy procedure above.
2. **`git pull` skipped.** The container source was old when you built.
3. **`docker compose build` reused a stale layer.** Try with `--no-cache`
   on the `COPY . /app` layer:
   ```bash
   docker compose build --no-cache info-broker-api
   ```
4. **Compose recreated the container against a stale image tag.** Force
   pull + recreate:
   ```bash
   docker compose up -d --force-recreate info-broker-api
   ```
5. **Tunnel not running.** `systemctl status cloudflared` (or the
   equivalent service manager) on the home server. If the tunnel is down,
   Cloudflare returns 502 — not 404 — so this is rarely the cause of a
   404, but worth a glance.

## Future improvement

The path forward is to add `.github/workflows/backend-deploy.yml` that,
on push to `main` matching backend paths, SSH'es into the home server
and runs the three commands above. Tracked at the top-level TODO list
when someone wants to spend an afternoon on it — until then, this
runbook is the contract.
