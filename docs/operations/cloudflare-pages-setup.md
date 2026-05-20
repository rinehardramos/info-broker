# Cloudflare Pages — Frontend Deploy

Step-by-step to get `infobroker.tech` serving the React frontend off Cloudflare Pages.
Time budget: ~25 minutes the first time.

## Prerequisites

- Cloudflare account (the same one that owns the existing R2 bucket).
- Domain `infobroker.tech` nameservers delegated to Cloudflare (see
  `[REDACTED:high-entropy-base64:35ch:hash=b6b9f4d6].md` § "Pointing domain.com at Cloudflare").
- `wrangler` installed (already done; `pnpm exec wrangler --version` works from `frontend/`).

## Two deployment modes

There are two valid paths to Pages. Pick one and stick with it.

### Path A — Git-connected (recommended for production)

Cloudflare watches your GitHub repo. Every push to `main` triggers a build in
Cloudflare's CI. Preview deploys auto-spawn for every other branch.

**Setup:**
1. Cloudflare dashboard → **Workers & Pages → Create → Pages → Connect to Git**.
2. Authorize GitHub. Select the `info-broker` (or `infobroker`) repo.
3. Project name: `info-broker`.
4. Production branch: `main`.
5. Build configuration:
   - Framework preset: **Vite**
   - Build command: `cd frontend && pnpm install && pnpm build`
   - Build output: `frontend/dist`
   - Root directory: `/` (leave default)
6. Environment variables (production scope):
   - `VITE_API_URL=https://api.infobroker.tech`
   - `NODE_VERSION=20`
7. **Save and Deploy**. First build takes ~3 minutes.
8. After it goes green, visit the `<project>.pages.dev` URL Cloudflare provides
   to confirm it works.

**Custom domain:**
9. In the Pages project → **Custom domains → Set up a domain** → enter
   `infobroker.tech`. Repeat for `www.infobroker.tech`.
10. Cloudflare wires DNS automatically because the zone is already managed.

**Pros:** zero local-machine dependency, every push deploys, preview URLs for
PRs are free, easy rollback to any previous deploy.

### Path B — Direct upload from local (emergencies / first-time bootstrap)

`pnpm wrangler pages deploy dist` from `frontend/` after a local build. Same
result as Path A but you deploy from your machine.

**Use when:**
- The Git-connected build broke and you need to hot-fix while debugging CI.
- You're doing the very first deploy and want to verify before flipping DNS.

**One-command flow (use the helper):**
```bash
# One-time login (browser will open)
cd frontend && pnpm exec wrangler login

# Subsequent deploys
./bin/cloudflare-pages-deploy.sh             # preview
./bin/cloudflare-pages-deploy.sh --production # production
```

The first deploy auto-creates the project if it doesn't exist. The script
bakes `VITE_API_URL=https://api.infobroker.tech` into the build.

## Verifying

After either path completes:
1. Visit the `<project>.pages.dev` URL. Should show the login screen.
2. Once `api.infobroker.tech` is tunneled (separate setup — see hybrid-architecture
   doc), confirm a login round-trips correctly.
3. Custom domain check: `https://infobroker.tech/` should now serve the same
   frontend, but proxied through Cloudflare's edge with TLS.

## Headers + redirects

`public/_headers` and `public/_redirects` ship in the build:

- **`_headers`** sets defensive baseline security headers
  (X-Frame-Options DENY, HSTS preload, strict referrer policy, no
  geolocation/camera/microphone permissions).
- **`_redirects`** has a single SPA-fallback rule: every path serves
  `/index.html` with a 200, so React Router can take over client-side.

Edit these in `frontend/public/`, redeploy.

## Common gotchas

- **TypeScript fails the build with `import.meta.env` errors** — `src/vite-env.d.ts`
  declares the type. If you add new `VITE_*` vars, add them to that file too.
- **API requests 404 in production** — `VITE_API_URL` wasn't set at build time.
  Confirm via `grep api.infobroker.tech frontend/dist/assets/*.js` after build.
- **Pages preview deploy can't reach api.infobroker.tech** — preview deploys hit
  the same prod API. If you want preview-only API, set per-environment
  `VITE_API_URL` in the dashboard.
- **CORS errors on first request** — `api.infobroker.tech` (FastAPI) must allow
  the Pages domain. Verify `[REDACTED:high-entropy-base64:33ch:hash=72fa00be]` allows `infobroker.tech`,
  `www.infobroker.tech`, and `*.pages.dev`.

## What this gives you

- **Edge-served frontend** with sub-100ms first-paint from PH.
- **Free TLS** (auto-renewed by Cloudflare).
- **Free DDoS + WAF** at the edge.
- **Free preview URLs** for every non-main branch.
- **One-click rollback** to any prior deploy in the dashboard.
- **Zero home-stack dependency** for static UI — even if your Legion box is
  offline, the frontend keeps serving (it just can't reach the API).
