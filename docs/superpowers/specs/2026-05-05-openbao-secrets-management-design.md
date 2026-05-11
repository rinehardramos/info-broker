# OpenBao Secrets Management Integration

**Date:** 2026-05-05
**Status:** Approved
**Scope:** Cross-project secrets management for info-broker and future projects

## Problem

Secrets are stored in plaintext `.env` files — vulnerable to dev machine compromise, tooling reads (e.g., Claude Code), accidental git commits, and CI/CD log leaks. Each project duplicates shared API keys with no central source of truth. No audit trail for secret access or changes.

## Decision

Integrate OpenBao (open-source Vault fork, MPL 2.0, Linux Foundation governed) as a centralized secrets service. One instance serves all projects. Each project authenticates via AppRole and reads only its allowed secret paths.

**Why OpenBao over alternatives:**
- vs HashiCorp Vault: same API, open-source license (MPL 2.0 vs BSL), no IBM lock-in
- vs SOPS + age: doesn't scale for multi-project shared secrets
- vs Infisical: heavier deps (Postgres + Redis), less mature ecosystem

## Architecture

```
                    OpenBao (:8200)
                    KV v2 engine
                         |
          +--------------+--------------+
          |              |              |
    secret/shared   secret/info-broker  secret/project-b
    (LLM keys,     (JWT_SECRET,        (project-specific)
     S3 creds)      DB creds)
          |              |              |
          v              v              v
     AppRole:        AppRole:       AppRole:
     info-broker     info-broker    project-b
     (reads shared   (reads both)   (reads shared
      + own path)                    + own path)
```

- **One OpenBao container** with file storage backend (upgradeable to Raft for HA)
- **AppRole auth** per project — role_id + secret_id (no human tokens in apps)
- **KV v2** — versioned key-value store with audit trail
- **Policy isolation** — each project can only read its own path + shared path

## Python Integration

### Secrets loader

**New file: `app/secrets.py`**

```python
"""
Thin OpenBao/Vault secrets loader.
Fetches secrets at startup via AppRole auth, injects into os.environ.
Falls back to existing env vars if OpenBao is not configured (local dev).
"""
import os
import logging

log = logging.getLogger(__name__)


def load_secrets() -> None:
    addr = os.getenv("OPENBAO_ADDR")
    role_id = os.getenv("OPENBAO_ROLE_ID")
    secret_id = os.getenv("OPENBAO_SECRET_ID")

    if not all([addr, role_id, secret_id]):
        log.info("OpenBao not configured - using env vars directly")
        return

    try:
        import hvac

        client = hvac.Client(url=addr)
        client.auth.approle.login(role_id=role_id, secret_id=secret_id)

        for path in ["shared", "info-broker"]:
            try:
                resp = client.secrets.kv.v2.read_secret_version(path=path)
                for key, value in resp["data"]["data"].items():
                    os.environ.setdefault(key, str(value))
                log.info("Loaded %d secrets from secret/%s", len(resp["data"]["data"]), path)
            except Exception as exc:
                log.warning("Failed to read secret/%s: %s", path, exc)

    except Exception as exc:
        log.error("OpenBao connection failed: %s - falling back to env vars", exc)
```

**Key design decisions:**
- `os.environ.setdefault` — doesn't override explicitly set env vars (container-level overrides still work)
- Graceful fallback — if OpenBao is down or unconfigured, existing env vars used. Local dev with `.env` unchanged.
- `hvac` library — standard Python client, works with both Vault and OpenBao identically

### Integration point

**File: `app/main.py`** — add at top of lifespan function:

```python
async def lifespan(app: FastAPI):
    from app.secrets import load_secrets
    load_secrets()
    # ... existing DB migration, startup logic ...
```

### Existing code changes

**None.** All 45+ files using `os.getenv()` continue unchanged. Secrets injected into `os.environ` before any code reads them.

## Docker Compose

### OpenBao service

```yaml
services:
  openbao:
    image: quay.io/openbao/openbao:latest
    cap_add: [IPC_LOCK]
    volumes:
      - openbao-data:/openbao/data
      - ./secrets/openbao-config.hcl:/openbao/config/config.hcl:ro
    ports:
      - "8200:8200"
    command: server
    restart: unless-stopped

volumes:
  openbao-data:
```

### OpenBao config

**New file: `secrets/openbao-config.hcl`**

```hcl
storage "file" {
  path = "/openbao/data"
}

listener "tcp" {
  address     = "0.0.0.0:8200"
  tls_disable = true  # TLS handled by reverse proxy in production
}

api_addr = "http://0.0.0.0:8200"
ui       = true
```

### info-broker service changes

```yaml
info-broker-api:
  environment:
    OPENBAO_ADDR: http://openbao:8200
    OPENBAO_ROLE_ID: ${OPENBAO_ROLE_ID}
    OPENBAO_SECRET_ID: ${OPENBAO_SECRET_ID}
    # Remove all 20+ individual secret env vars
  depends_on:
    - openbao
```

**Before:** 20+ secrets in docker-compose environment block + `.env`.
**After:** 3 bootstrap vars (addr, role_id, secret_id). Everything else from OpenBao.

## Bootstrap

**New file: `scripts/openbao-init.sh`**

One-time setup:

1. Initialize: `bao operator init -key-shares=1 -key-threshold=1`
2. Unseal: `bao operator unseal <key>`
3. Enable KV v2: `bao secrets enable -path=secret kv-v2`
4. Enable AppRole: `bao auth enable approle`
5. Create policy:
   ```hcl
   path "secret/data/shared/*" { capabilities = ["read"] }
   path "secret/data/info-broker/*" { capabilities = ["read"] }
   ```
6. Create role: `bao write auth/approle/role/info-broker token_ttl=1h token_max_ttl=4h policies=info-broker`
7. Get credentials: `bao read auth/approle/role/info-broker/role-id` + `bao write -f auth/approle/role/info-broker/secret-id`
8. Seed secrets: `bao kv put secret/shared ANTHROPIC_API_KEY=... OPENAI_API_KEY=...`

### Adding a new project

```bash
# 1. Create policy
bao policy write project-b - <<EOF
path "secret/data/shared/*" { capabilities = ["read"] }
path "secret/data/project-b/*" { capabilities = ["read"] }
EOF

# 2. Create AppRole
bao write auth/approle/role/project-b policies=project-b

# 3. Get credentials for project-b's docker-compose
bao read auth/approle/role/project-b/role-id
bao write -f auth/approle/role/project-b/secret-id

# 4. Seed project-specific secrets
bao kv put secret/project-b DB_NAME=project_b
```

## Security model

| Threat | Mitigation |
|--------|-----------|
| Dev machine compromise | No plaintext `.env` with all secrets. Only role_id + secret_id on dev machines. |
| Tooling reads (Claude Code) | Tools see only OPENBAO_ROLE_ID + OPENBAO_SECRET_ID, not actual API keys |
| Git commit leak | No secrets in git. OpenBao is the source of truth. |
| Log/CI exposure | Secrets fetched at runtime, never in build args or compose files |
| Runtime interception | AppRole tokens have 1h TTL, auto-expire. Secrets in process env vars (same as current). |
| OpenBao compromise | File storage encrypted at rest. Access policies limit blast radius per project. |

## Secrets inventory migration

### Shared secrets (secret/shared/)

| Key | Current source |
|-----|---------------|
| ANTHROPIC_API_KEY | .env |
| OPENAI_API_KEY | .env |
| OPENROUTER_API_KEY | .env |
| GEMINI_API_KEY | .env |
| S3_ACCESS_KEY_ID | .env |
| S3_SECRET_ACCESS_KEY | .env |
| S3_BUCKET | .env |
| S3_ENDPOINT | .env |
| APIFY_API_TOKEN | .env |
| NEWSAPI_KEY | .env |
| OPENWEATHER_API_KEY | .env |

### Project-specific secrets (secret/info-broker/)

| Key | Current source |
|-----|---------------|
| INFO_BROKER_API_KEY | .env |
| JWT_SECRET | .env |
| POSTGRES_PASSWORD | docker-compose.yml |
| POSTGRES_USER | docker-compose.yml |
| POSTGRES_DB | docker-compose.yml |

### Non-secret config (remain as env vars)

| Key | Reason |
|-----|--------|
| POSTGRES_HOST | Service discovery, not secret |
| POSTGRES_PORT | Port config |
| QDRANT_HOST / QDRANT_PORT | Service discovery |
| TEMPORAL_HOST / TEMPORAL_PORT | Service discovery |
| LLM_PROVIDER | Feature config |
| VITE_API_TARGET / VITE_WS_URL | Frontend config |

## File changes summary

| File | Change |
|------|--------|
| `app/secrets.py` | **New** — secrets loader (30 lines) |
| `app/main.py` | Add `load_secrets()` to lifespan (2 lines) |
| `docker-compose.yml` | Add openbao service, simplify env vars |
| `secrets/openbao-config.hcl` | **New** — OpenBao server config |
| `scripts/openbao-init.sh` | **New** — bootstrap script |
| `pyproject.toml` | Add `hvac` dependency |
| `.env.example` | Update to show only bootstrap vars |

## Testing

- **Unit:** Mock `hvac.Client` — verify env var injection, fallback behavior, error handling
- **Integration:** Start OpenBao in Docker, seed test secrets, verify `load_secrets()` populates env
- **E2E:** Full stack with OpenBao — verify API starts and serves requests using OpenBao-sourced secrets
- **Fallback:** Verify app starts normally without OpenBao configured (local dev mode)

## Future enhancements (not in scope)

- Auto-unseal via cloud KMS (AWS, GCP, Azure)
- Dynamic database credentials (OpenBao generates temp Postgres users)
- Secret rotation notifications via WebSocket
- OpenBao UI accessible from info-broker settings page
- Raft storage backend for HA (when moving beyond single-node)
