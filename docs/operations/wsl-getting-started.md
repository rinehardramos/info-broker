# Getting Started on WSL2 / Windows 11

How to run Info-Broker on a Lenovo Legion 5 (16 GB RAM) or similar Windows
machine via WSL2 + Docker Desktop. Assumes you've never run it locally before.

> If you're on macOS, ignore this doc and follow `docs/getting-started.md`.

## TL;DR

```powershell
# In Windows PowerShell (admin, one-time):
wsl --install -d Ubuntu-24.04
# Then create C:\Users\<you>\.wslconfig with the snippet below, restart WSL.
```

```bash
# In WSL Ubuntu (one-time):
cd ~ && git clone <repo-url> info-broker && cd info-broker
claude auth login                    # subscription auth, one-time
./bin/wsl-bootstrap.sh
# → http://localhost:5173 opens in Windows Chrome
```

That's it. Stop reading here if everything works. Below are the details for
when something doesn't.

---

## 1. Prerequisites

| Tool | Version | Why |
|---|---|---|
| Windows 11 | 22H2+ | WSL2 GA |
| WSL2 + Ubuntu 24.04 | latest | Linux userland |
| Docker Desktop | 4.30+ | WSL2 backend enabled |
| Git | any | clone repo inside WSL |
| Claude Code CLI | 0.5+ | subscription auth path |

## 2. WSL memory budget — the critical first step

WSL2 takes up to 50% of host RAM by default (8 GB on a 16 GB machine).
With Docker Desktop's overhead and your browser, that's tight. Cap it
explicitly to leave headroom.

Create `C:\Users\<you>\.wslconfig`:

```ini
[wsl2]
memory=12GB
processors=6
swap=4GB
localhostForwarding=true
```

Then restart WSL:

```powershell
wsl --shutdown
```

Verify after WSL comes back:

```bash
free -h        # Should show ~12GB total
```

## 3. Filesystem placement — the silent killer

**Clone the repo inside WSL (`~/projects/info-broker`), NOT on `/mnt/c/...`.**

Cross-filesystem (`/mnt/c`) goes through the 9P bridge, which is 10–50× slower
for read-heavy work (Vite HMR, pytest, Postgres). Symptoms: HMR takes 10s per
keystroke, Postgres queries crawl.

```bash
# Inside WSL Ubuntu, NOT Windows Explorer:
cd ~ && mkdir -p projects && cd projects
git clone <repo-url> info-broker
cd info-broker
git config --global core.autocrlf input   # LF endings, not CRLF
```

VS Code: install the "WSL" extension on Windows side, then `code .` from
inside WSL opens the project with the IDE talking to WSL natively.

## 4. Docker Desktop settings

- **Settings → Resources → WSL Integration**: enable for your Ubuntu distro.
- **Settings → General → Use containerd for pulling and storing images**: on.
- **Settings → Resources → Advanced**: leave defaults — `.wslconfig` is the
  source of truth. Don't set memory in two places.

## 5. Claude Code authentication

Three valid paths, in priority order:

### Path A — Interactive login (recommended)

```bash
# Inside WSL
npm install -g @anthropic-ai/claude-code     # if not already installed
claude auth login                            # browser flow
```

Credentials land at `~/.config/anthropic/credentials.json`. The
`./bin/wsl-bootstrap.sh` script automatically mounts this read-only into the
brain worker containers, and `app/claude_auth_setup.py` copies them into the
container-internal `/root/.claude/` so Claude Code can refresh tokens.

### Path B — Environment variable

```bash
# Append to .env
echo "CLAUDE_CODE_OAUTH_REFRESH_TOKEN=<token>" >> .env
```

Useful for CI or when copying creds from another already-logged-in machine
(read the file at `~/.config/anthropic/credentials.json`, find the refresh token,
paste it into the env var).

### Path C — Anthropic API key (different cost model)

```bash
echo "ANTHROPIC_API_KEY=sk-ant-api-..." >> .env
```

This bypasses subscription quota entirely. Billed against your Anthropic API
budget. Use when you want per-user BYOK or when subscription throughput is
the bottleneck.

## 6. Run it

```bash
./bin/wsl-bootstrap.sh                  # default: pg + qdrant + temporal + workers + api + frontend
./bin/wsl-bootstrap.sh --with graph     # also enable neo4j (knowledge graph surface)
./bin/wsl-bootstrap.sh --with ui        # also enable Temporal UI (debugging)
./bin/wsl-bootstrap.sh --with tunnel    # also enable Cloudflare Tunnel (requires CLOUDFLARED_TOKEN)
```

Visit:
- Frontend: `http://localhost:5173` (Windows browsers can reach this directly
  via WSL's localhost forwarding)
- API: `http://localhost:8000`
- API docs: `http://localhost:8000/docs`

## 7. Memory budget by service (default profile)

| Service | Reservation | Limit |
|---|---:|---:|
| postgres | 512 MB | 1 GB |
| qdrant | 256 MB | 1 GB |
| temporal | 512 MB | 1 GB |
| info-broker-api | 384 MB | 1 GB |
| temporal-worker | 256 MB | 768 MB |
| is-temporal-worker | 1.5 GB | 3 GB |
| frontend (dev) | 256 MB | 1 GB |
| **Total default** | **~3.7 GB** | **~8.8 GB** |

Adding `--with graph` adds 768 MB / 1.5 GB for neo4j. Don't enable on 16 GB
unless you actively need the knowledge-graph surface — PKG covers absorption
needs without it.

## 8. Troubleshooting

### "Cannot connect to the Docker daemon"
Docker Desktop isn't running, or WSL integration isn't enabled for your distro.
Settings → Resources → WSL Integration → toggle your distro on.

### Vite HMR is sluggish
Repo is probably on `/mnt/c/`. Clone again inside the WSL filesystem.

### `info-broker-api` keeps restarting
Check logs: `docker compose logs info-broker-api`. Most common: missing
`GEMINI_API_KEY` in `.env`, or Postgres still booting (rare).

### Brain runs fail with auth errors
Run `docker compose exec is-temporal-worker python -c "from app.claude_auth_setup import ensure_claude_credentials; print(ensure_claude_credentials())"` — should print one of `api_key | oauth_env | host_mount | preseeded`. If it prints `none`, see Section 5.

### Time drift breaks OAuth / TLS after Windows sleep
```bash
sudo hwclock -s          # one-off resync
```
Add to `.bashrc` if it happens often.

### Port 5173 / 8000 already in use
Some other process. Find it via `netstat -ano | findstr :5173` in PowerShell
or kill the offending compose stack: `docker compose ls` then `docker compose
-p <name> down`.

### Clock-on-screen out of date after a long sleep
WSL time can drift. `sudo hwclock -s` fixes it immediately.

## 9. Updating

```bash
cd ~/projects/info-broker
git pull
./bin/wsl-bootstrap.sh     # idempotent — rebuilds + reapplies migrations
```

## 10. Stopping / cleaning up

```bash
docker compose down                      # stop containers, keep volumes
docker compose down -v                   # also remove volumes (DESTRUCTIVE)
docker system prune -af --volumes        # nuke everything (DESTRUCTIVE)
```

## 11. Public access via Cloudflare Tunnel (optional)

See `docs/operations/hybrid-architecture.md` for the full setup. Short version:

1. Cloudflare Zero Trust → Networks → Tunnels → Create. Copy the token.
2. Add to `.env`: `CLOUDFLARED_TOKEN=<token>`.
3. Configure ingress in the Cloudflare dashboard:
   - `api.infobroker.net` → `http://info-broker-api:8000`
   - `temporal.infobroker.net` → `http://temporal-ui:8080`
4. Run: `./bin/wsl-bootstrap.sh --with tunnel --with ui`
5. Verify in dashboard the tunnel shows as healthy.
