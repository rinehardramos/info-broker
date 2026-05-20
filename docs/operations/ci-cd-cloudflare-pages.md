# CI/CD — GitHub Actions → Cloudflare Pages

Pipeline at `.github/workflows/cloudflare-pages.yml`.

## What it does

| Trigger | Action |
|---|---|
| Push to `main` | Production deploy → `infobroker.tech` + `info-broker.pages.dev` |
| Pull request | Preview deploy → `<hash>.info-broker.pages.dev`, URL posted as a PR comment |
| Manual via Actions tab | `workflow_dispatch` — same as push to current branch |

Each run does, in order:
1. **Checkout** at depth 1 (shallow; deploy doesn't need history).
2. **pnpm install** with `--frozen-lockfile` against `frontend/pnpm-lock.yaml`. Cached by setup-node so cold builds drop from ~90s to ~10s after the first run.
3. **TypeScript check** — `pnpm tsc --noEmit`. Build is gated on TS clean.
4. **Vite build** with `VITE_API_URL=https://api.infobroker.tech` baked in. Optional per-branch override via the repo variable `VITE_API_URL_OVERRIDE`.
5. **Sanity check** — grep the built bundle for `api.infobroker.tech`; refuse to deploy if missing. Also asserts `dist/_headers` and `dist/_redirects` shipped.
6. **Deploy** via `cloudflare/wrangler-action@v3`. Branch name routes to the right Pages environment (main → production, others → preview).
7. **Summary** to the Actions UI with branch, commit, deployment URL.

Concurrency: superseded runs are cancelled (`pages-<ref>` group). Total budget per run: 10 minutes.

## One-time setup

### 1. Create a Cloudflare API token (~2 minutes)

Go to **My Profile → API Tokens → Create Token → Use template "Edit Cloudflare Workers"** OR build from scratch with these scopes:

| Scope | Permission |
|---|---|
| Account → Cloudflare Pages | Edit |
| Account → Account Settings | Read |
| Zone → Workers Scripts (optional, if Workers added later) | Edit |

Account resources: include your account. Zone resources: include `infobroker.tech` (and `infobroker.net` if you kept it).

Copy the token — Cloudflare shows it once.

### 2. Add GitHub secrets (~30 seconds)

Repo → Settings → Secrets and variables → Actions → New repository secret:

| Name | Value |
|---|---|
| `CLOUDFLARE_API_TOKEN` | The token from step 1 |
| `CLOUDFLARE_ACCOUNT_ID` | Your 32-char account ID (visible in `wrangler whoami` or the Cloudflare dashboard URL) |

### 3. Push a commit to trigger the first run

```bash
git commit --allow-empty -m "ci: trigger first Pages CI run"
git push
```

Watch the workflow in the Actions tab. First run rebuilds + deploys (~2 min); subsequent runs hit the pnpm cache and run faster (~45 s).

## Troubleshooting

### "Authentication error: Token is missing"
Secret name typo. The workflow expects exactly `CLOUDFLARE_API_TOKEN` (not `[REDACTED:high-entropy-base64:20ch:hash=53538d15]_KEY` or `CF_TOKEN`).

### "Project not found: info-broker"
Either the Cloudflare project wasn't created (run `[REDACTED:high-entropy-base64:27ch:hash=f8f5d040].sh --create` once locally), or the token doesn't have Pages:Edit scope.

### Build fails with "VITE_API_URL was not baked into the build"
The Vite build silently ignored the env var. Either Vite's `import.meta.env` isn't being read at runtime, or the env var name doesn't start with `VITE_`. Verify `[REDACTED:high-entropy-base64:25ch:hash=2ad6da66]:7` reads `import.meta.env.VITE_API_URL`.

### PR preview URL not posted as comment
GitHub permissions issue. Verify `permissions: pull-requests: write` is present at the workflow root. If your org disabled Action PR comments globally, the deploy still succeeds; the URL is just not auto-posted.

### "Resource not accessible by integration"
Repo Settings → Actions → General → Workflow permissions → set to "Read and write permissions". Default is too restrictive on some orgs.

## Local equivalent

The CI deploy is functionally identical to running `./bin/cloudflare-pages-deploy.sh --production` from a logged-in laptop. The script and the workflow share `VITE_API_URL=https://api.infobroker.tech`, the same `dist` output, the same `--project-name=info-broker`.

Difference: CI authenticates via API token (no OAuth flow), and runs on Linux instead of macOS — but the Pages output is byte-for-byte the same.

## Rollback

In the Cloudflare Pages dashboard → `info-broker` project → Deployments → find the last-good deploy → **Rollback to this deployment**. One click, no rebuild. Or via the workflow: revert the commit, push, the new build deploys.

## What this commit does NOT change

- The frontend `bin/cloudflare-pages-deploy.sh` script stays as the local manual escape hatch. CI is additive.
- The Cloudflare Tunnel (`cloudflared` on Legion) is independent; CI doesn't touch it.
- Backend / API is not deployed by this workflow. Backend stays on the home Legion box; CI only handles the static frontend.
