# Security Hardening Design Spec

**Date:** 2026-05-13
**Status:** Design — ready for implementation
**Owner:** Platform / Security
**Audience:** Sonnet coding agent (implementation), Reviewers

## 1. Goal and scope

Harden the info-broker platform across five tightly-scoped surfaces:

1. Password hashing (move from bcrypt to Argon2id with auto-upgrade).
2. Input sanitization (server-side + client-side; user inputs only — never scraped/LLM content).
3. MCP request authentication (HMAC-SHA256 with replay protection).
4. Org/tenant isolation gaps (5 confirmed query sites missing `org_id` scope).
5. API hardening (CORS lockdown, rate limiting on password change, Pydantic length caps, JWT exp verification).

Non-goals:

- No new auth framework, no OAuth/SSO rollout.
- No re-encryption of data at rest.
- No changes to scraped-content sanitization rules (these remain raw on purpose; sanitization is only render-time on the frontend for research content).
- No migration script for existing bcrypt password hashes — they upgrade lazily on next successful login.

## 2. Architecture decisions

### 2.1 Password hashing

**Decision:** Use `passlib.CryptContext(schemes=["argon2", "bcrypt"], deprecated=["bcrypt"])`.

**Rationale:** Argon2id is the OWASP-recommended modern password hash (2024 guidance) and the winner of the Password Hashing Competition. Listing `bcrypt` as a known but deprecated scheme means:

- New hashes are written with Argon2id.
- Existing bcrypt hashes still verify (no forced re-auth, no migration script).
- `ctx.needs_update(hash)` returns `True` for bcrypt hashes; on successful login we re-hash with Argon2id and persist. Within one login cycle per user, every active account is upgraded.

**Parameters (OWASP 2024 baseline):**

- `memory_cost = 65536` (64 MiB)
- `time_cost = 3`
- `parallelism = 4`

These are encoded in `passlib` as `argon2__memory_cost`, `argon2__time_cost`, `argon2__parallelism`.

### 2.2 Input sanitization strategy

**Decision: Option C — strict-at-write for user inputs, render-time for research content.**

Rejected alternatives:

- *Option A — sanitize all writes:* corrupts scraped HTML/markdown that downstream nodes need raw (LinkedIn snippets, structured tool outputs).
- *Option B — sanitize at render only:* puts the entire defensive surface on the React layer; any non-React consumer (MCP, exports, future mobile) is unprotected.

Option C splits responsibility cleanly:

- **User-submitted free-text** (chat messages, pipeline names, source names, settings strings) is sanitized at the FastAPI ingress via Pydantic validators. It is never stored with HTML — there is no legitimate reason for a user to inject markup into a pipeline name.
- **Research artifacts** (scraped pages, LLM responses, fused intelligence) are stored verbatim — their fidelity matters — and sanitized at render time in React via DOMPurify.

This means a malicious source page cannot store XSS that survives into the React renderer, and a malicious user cannot store XSS in a field another user might see in the UI.

### 2.3 MCP authentication

**Decision:** Layer HMAC-SHA256 request signing on top of the existing bearer token, mirroring `app/services/webhook.py`.

**Rationale:** Bearer tokens alone are vulnerable to log exfiltration and TLS-terminating proxies. HMAC over `timestamp + "." + body` with a shared `MCP_SIGNING_SECRET`:

- Binds each request to its body (tampering invalidates signature).
- Binds each request to a 5-minute time window (replay protection).
- Reuses the proven pattern already in production for outbound webhooks.

The bearer token is retained for coarse identity; the HMAC adds integrity + freshness.

### 2.4 Superadmin tenancy model

**Decision:** Add a single helper, `org_scope_clause(user)`, that returns a SQL fragment + parameters. `is_admin=True` users get an empty fragment (sees all). All other users get `AND org_id = %s` bound to their `user_org_id`.

**Rationale:** Centralizes the "superadmin bypass" rule so every query site looks identical and the policy is auditable from one function. Avoids per-route `if user.is_admin` branches that historically drift.

`research_trails` has no `org_id` column, so its scope is enforced via JOIN on `pipeline_runs`, which does have `org_id`. We do NOT add `org_id` to `research_trails` — denormalization risks divergence; JOIN keeps `pipeline_runs` as the single source of truth for ownership.

### 2.5 Rejected: WAF, CSP nonces, hCaptcha on login

Out of scope for this pass. CSP hardening is tracked separately; WAF is a deployment concern, not application code; hCaptcha needs UX review.

## 3. Implementation plan

### 3.1 Password hashing — Argon2id

**File: `requirements.txt` (root)**

Add:

```
argon2-cffi>=23.1.0
```

**File: `app/routers/v3/auth.py`**

Replace the existing `CryptContext` initialization:

```python
# Before
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# After
pwd_context = CryptContext(
    schemes=["argon2", "bcrypt"],
    deprecated=["bcrypt"],
    argon2__memory_cost=65536,
    argon2__time_cost=3,
    argon2__parallelism=4,
)
```

**Auto-upgrade logic on successful login**

Inside the existing login handler in `app/routers/v3/auth.py`, after `pwd_context.verify(...)` returns `True`:

```python
if pwd_context.needs_update(user["password_hash"]):
    new_hash = pwd_context.hash(plaintext_password)
    # Use the existing DB cursor / session pattern from the file
    cursor.execute(
        "UPDATE ui_users SET password_hash = %s WHERE id = %s",
        (new_hash, user["id"]),
    )
```

Do **not** rehash on failed login. Do **not** rehash if `needs_update` returns `False` (no-op churn).

**Password validation**

Add a Pydantic validator on the password field of both the registration model and the new password-change model:

```python
import re

def _validate_password_strength(v: str) -> str:
    if len(v) < 12:
        raise ValueError("Password must be at least 12 characters")
    if not re.search(r"[\d\W]", v):
        raise ValueError("Password must contain at least one digit or special character")
    return v
```

Apply via `@field_validator("password")` and `@field_validator("new_password")`.

**New endpoint: `POST /v3/auth/change-password`**

Location: `app/routers/v3/auth.py`.

```python
class ChangePasswordIn(BaseModel):
    current_password: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def _strong(cls, v: str) -> str:
        return _validate_password_strength(v)

@router.post("/change-password")
@limiter.limit("5/minute")  # use existing slowapi limiter
async def change_password(
    request: Request,
    body: ChangePasswordIn,
    user: dict = Depends(require_analyst_user),
):
    # Fetch current hash for user["id"]
    # Verify body.current_password against stored hash; 401 on mismatch
    # Reject if new_password == current_password (compare verify against new)
    # Hash new_password with pwd_context, persist via UPDATE ui_users
    # Return {"ok": True}
```

Required for SOC 2 Type 2 (CC6.1).

### 3.2 Input sanitization

#### Backend — `bleach`

**File: `requirements.txt`**

Add:

```
bleach>=6.1.0
```

**File: `app/security.py` (new)**

```python
"""Input sanitization helpers.

Use sanitize_user_input on user-submitted free-text BEFORE persisting.
Never apply to scraped HTML, LLM completions, or any research artifact —
those must be stored raw and sanitized at render time on the frontend.
"""

from __future__ import annotations

import bleach

DEFAULT_MAX_LENGTH = 4000


def sanitize_user_input(value: str, max_length: int = DEFAULT_MAX_LENGTH) -> str:
    """Strip all HTML tags and truncate. Idempotent.

    - Removes all tags and attributes (whitelist is empty).
    - strip=True removes tag bodies that look like dangling HTML.
    - Truncation is applied AFTER cleaning so the cap reflects stored size.
    """
    if value is None:
        return ""
    cleaned = bleach.clean(value, tags=[], attributes={}, strip=True)
    return cleaned[:max_length]
```

**Apply via Pydantic `field_validator`**

The following request models receive a validator. Implementation hint: define a single reusable validator factory at module top, then attach via `@field_validator(...)` with the appropriate `max_length`.

| File | Model | Field | max_length |
|---|---|---|---|
| `app/routers/v3/agent.py` | `AgentMessageIn` | `message` | 8000 |
| `app/routers/v3/pipelines.py` | pipeline create/update model | `name` | 255 |
| `app/routers/v3/pipelines.py` | pipeline create/update model | `description` | 4000 |
| `app/routers/v3/sources_api.py` | source create/update model | `name` | 255 |
| `app/routers/v3/sources_api.py` | source create/update model | `description` | 4000 |
| Settings models in `app/routers/v3/` (search for `class.*Settings.*BaseModel`) | All free-text string fields | 4000 |

Implementation hint for the agent: search for `class .*In\(BaseModel\)` and `class .*Update\(BaseModel\)` under `app/routers/v3/` and add validators to any model that touches a user-controlled string field. Do NOT add validators to models that wrap scraped/LLM outputs.

**Do NOT apply** to:

- `app/sources/parser.py` outputs
- Scraper node results in `app/pipeline/nodes/`
- LLM completion responses cached in any table
- Research trail entries

#### Frontend — `dompurify`

**File: `frontend/package.json`**

Add to `dependencies`:

```json
"dompurify": "^3.2.0"
```

Add to `devDependencies`:

```json
"@types/dompurify": "^3.0.5"
```

**File: `frontend/src/lib/sanitize.ts` (new)**

```ts
import DOMPurify from "dompurify";

/**
 * Sanitize untrusted HTML before insertion via dangerouslySetInnerHTML
 * or before rendering markdown-derived HTML from research artifacts.
 *
 * Use for: research results, LLM-rendered markdown, scraped snippets.
 * Do NOT use for: user-submitted strings (those are already sanitized server-side).
 */
export const safe = (html: string): string => DOMPurify.sanitize(html);
```

**Apply at every `dangerouslySetInnerHTML` site**

Implementation hint: `grep -rn "dangerouslySetInnerHTML" frontend/src/` and wrap each `__html: <expr>` as `__html: safe(<expr>)`.

Apply also to markdown renderer output for research result panels. Inspect at minimum:

- `frontend/src/components/results/ResultsPanel.tsx`
- `frontend/src/components/results/ResearchFlow.tsx`
- `frontend/src/components/live/LiveStream.tsx`
- `frontend/src/components/agent/AgentChat.tsx`

Any markdown-to-HTML pipeline (e.g. `marked`, `react-markdown` with `rehype-raw`) must pass the output through `safe()` before injection.

### 3.3 MCP authentication — HMAC-SHA256

**File: `mcp_server/client.py`**

Add request signing to every outbound API call:

```python
import hmac
import hashlib
import os
import time

_MCP_SECRET = os.environ.get("MCP_SIGNING_SECRET", "")

def _sign_request(body: bytes) -> dict[str, str]:
    if not _MCP_SECRET:
        return {}  # dev mode — server will warn
    ts = str(int(time.time()))
    mac = hmac.new(
        _MCP_SECRET.encode("utf-8"),
        f"{ts}.".encode("utf-8") + body,
        hashlib.sha256,
    ).hexdigest()
    return {
        "X-MCP-Timestamp": ts,
        "X-MCP-Signature": f"sha256={mac}",
    }
```

Merge the dict returned by `_sign_request(body_bytes)` into the existing headers (alongside `Authorization: Bearer ...`) on every request the client makes. The body passed to `_sign_request` must be the **exact** bytes sent on the wire (after JSON serialization, before TLS). If the HTTP client serializes internally, pre-serialize and pass `data=body_bytes` instead of `json=obj`.

**File: `app/routers/v3/mcp_auth.py` (new)**

```python
"""HMAC-SHA256 verification for MCP requests.

Mirrors app/services/webhook.py signing pattern. Wraps existing bearer-token
auth — does not replace it. Bearer identifies the caller; HMAC proves the
request body is intact and recent.
"""

from __future__ import annotations

import hmac
import hashlib
import logging
import os
import time

from fastapi import Header, HTTPException, Request

log = logging.getLogger(__name__)

_MCP_SECRET = os.environ.get("MCP_SIGNING_SECRET", "")
_MAX_SKEW_SECONDS = 300

if not _MCP_SECRET:
    log.warning(
        "MCP_SIGNING_SECRET not set — MCP request signing is DISABLED. "
        "This is acceptable in development only."
    )


async def verify_mcp_signature(
    request: Request,
    x_mcp_signature: str | None = Header(default=None),
    x_mcp_timestamp: str | None = Header(default=None),
) -> None:
    if not _MCP_SECRET:
        return  # dev mode bypass

    if not x_mcp_signature or not x_mcp_timestamp:
        raise HTTPException(status_code=401, detail="missing MCP signature headers")

    try:
        ts = int(x_mcp_timestamp)
    except ValueError:
        raise HTTPException(status_code=401, detail="invalid MCP timestamp")

    if abs(time.time() - ts) > _MAX_SKEW_SECONDS:
        raise HTTPException(status_code=401, detail="MCP timestamp outside window")

    body = await request.body()
    expected = hmac.new(
        _MCP_SECRET.encode("utf-8"),
        f"{ts}.".encode("utf-8") + body,
        hashlib.sha256,
    ).hexdigest()

    provided = x_mcp_signature.removeprefix("sha256=")
    if not hmac.compare_digest(expected, provided):
        raise HTTPException(status_code=401, detail="MCP signature mismatch")
```

**Apply to MCP-facing routes**

Add `Depends(verify_mcp_signature)` to every route under `/v3/mcp/*`. Implementation hint: search for routers registered under the `/v3/mcp` prefix (likely in `app/main.py` or `app/routers/v3/__init__.py`) and either:

- Attach the dependency at the router level: `APIRouter(prefix="/v3/mcp", dependencies=[Depends(verify_mcp_signature)])`, OR
- Add it per-endpoint if a router-level attachment is impractical.

Router-level is preferred for blast-radius reasons.

**Env var**

Document `MCP_SIGNING_SECRET` in:

- `docker-compose.yml` (under both `api` and `mcp_server` service env)
- `.env.example` (if present) with a comment: `# 32+ byte random hex; generate with: openssl rand -hex 32`

### 3.4 Org/tenant isolation

**File: `app/routers/v3/tenancy.py`**

Add the helper:

```python
def org_scope_clause(user: dict) -> tuple[str, list]:
    """Return (sql_fragment, params) for org scoping.

    Superadmin (is_admin=True) sees all orgs — returns empty fragment.
    All other users are scoped to their own org_id.

    Usage:
        clause, params = org_scope_clause(user)
        cursor.execute(
            f"SELECT * FROM pipelines WHERE id = %s {clause}",
            [pipeline_id, *params],
        )
    """
    if user.get("is_admin"):
        return ("", [])
    return ("AND org_id = %s", [user_org_id(user)])
```

**Fix each identified gap**

#### Gap 1 — `app/routers/v3/research_api.py:57`

Current query (paraphrased):

```python
cursor.execute(
    "SELECT * FROM research_trails WHERE run_id = %s",
    (run_id,),
)
```

Fixed query:

```python
clause, params = org_scope_clause(user)
cursor.execute(
    f"""
    SELECT rt.*
    FROM research_trails rt
    JOIN pipeline_runs pr ON pr.id = rt.run_id
    WHERE rt.run_id = %s {clause.replace("org_id", "pr.org_id")}
    """,
    [run_id, *params],
)
```

Implementation hint: because `research_trails` has no `org_id`, the join is mandatory and the helper's `org_id` placeholder must be qualified to `pr.org_id`. The simplest pattern is to call the helper, then `str.replace("AND org_id", "AND pr.org_id")` on the fragment. Yes, this is mildly ugly; the alternative (a second helper) is worse.

Apply the same pattern to:

- `app/routers/v3/research_api.py:116`
- `app/routers/v3/research_api.py:139`
- `app/routers/v3/pipelines.py:330`
- `app/routers/v3/exports.py:47`

#### Gap 2 — `app/routers/v3/pipelines.py:366`

Current:

```python
cursor.execute(
    "SELECT * FROM pipelines WHERE user_id = %s OR is_system = TRUE",
    (user_id,),
)
```

Fixed:

```python
clause, params = org_scope_clause(user)
cursor.execute(
    f"""
    SELECT * FROM pipelines
    WHERE (user_id = %s OR is_system = TRUE)
      AND (TRUE {clause})
    """,
    [user_id, *params],
)
```

Note: `is_system = TRUE` pipelines are global by design (shared templates). They remain visible to all users. The `AND (TRUE {clause})` form short-circuits cleanly when `clause` is empty (superadmin) and adds `AND TRUE AND org_id = %s` for everyone else — semantically equivalent to `AND org_id = %s`.

If business policy says system pipelines should also be org-scoped, change to:

```python
WHERE (user_id = %s OR (is_system = TRUE AND org_id IS NULL)) AND ...
```

— but absent a product decision, retain current visibility.

#### Gap 3 — `app/routers/v3/sources_api.py:264`

Current:

```python
cursor.execute(
    "SELECT * FROM research_sources WHERE id = %s",
    (source_id,),
)
```

Fixed:

```python
clause, params = org_scope_clause(user)
cursor.execute(
    f"SELECT * FROM research_sources WHERE id = %s {clause}",
    [source_id, *params],
)
```

If the resulting rowcount is 0 and `clause` was non-empty, return 404 (do not leak existence to non-owning org).

**Audit followup**

After fixes, add a regression check. Implementation hint:

```bash
rg -n "WHERE\s+\w+\s*=\s*%s" app/routers/v3/ | rg -v "org_id|org_scope_clause"
```

Any hit on a tenant-scoped table (`pipelines`, `pipeline_runs`, `research_trails`, `research_sources`, `agent_sessions`, `agent_messages`, settings tables) is a regression and must be fixed before merge. Add this `rg` invocation to `tasks/lessons.md` so it survives.

### 3.5 API security hardening

#### CORS

**File: `app/main.py`**

Replace any wildcard CORS config with an env-driven origin list:

```python
import os

_frontend_url = os.environ.get("FRONTEND_URL", "http://localhost:5173")
_allowed_origins = [o.strip() for o in _frontend_url.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-MCP-Signature", "X-MCP-Timestamp"],
)
```

`FRONTEND_URL` supports comma-separated values to allow staging + prod from a single deployment config.

#### Rate limiting

Confirm the existing `slowapi` limiter is wired in `app/main.py`. If `Depends(limiter)` is already applied to `/v3/auth/login`, verify the rule is `10/5minutes` per IP. If not, set it.

For `/v3/auth/change-password`: `@limiter.limit("5/minute")` per IP. Rationale: password change is interactive, never machine-driven; 5/min is generous for a human and tight against scripted abuse.

#### Pydantic max_length

Apply `Field(..., max_length=N)` on every uncapped free-text field. Implementation hint: `rg -n "BaseModel" app/routers/v3/ -l` then audit each model. Defaults:

- Chat / agent messages: 8000
- Names (pipeline, source, org, user): 255
- Descriptions: 4000
- Config / settings strings: 4000

This is belt-and-suspenders alongside the `sanitize_user_input` truncation — Pydantic catches oversize at parse time (400 response) before sanitization runs.

#### JWT

**File: `app/routers/v3/auth.py`**

In the JWT issuance path:

```python
from datetime import datetime, timezone, timedelta

now = datetime.now(timezone.utc)
payload = {
    "sub": str(user["id"]),
    "org_id": str(user["org_id"]),
    "is_admin": bool(user["is_admin"]),
    "role": user["role"],
    "iat": int(now.timestamp()),
    "exp": int((now + timedelta(hours=8)).timestamp()),
}
```

In the JWT decode path (likely the dependency that produces the `user` dict):

```python
import jwt

try:
    payload = jwt.decode(
        token,
        JWT_SECRET,
        algorithms=["HS256"],
        options={"require": ["exp", "iat", "sub"]},
    )
except jwt.ExpiredSignatureError:
    raise HTTPException(401, "token expired")
except jwt.InvalidTokenError:
    raise HTTPException(401, "invalid token")
```

`options={"require": [...]}` ensures decode fails if `exp` is missing — closes a class of forged-token bugs where a token lacking `exp` would otherwise be accepted indefinitely.

## 4. Testing requirements

For each change, the agent MUST add or update tests under `tests/`.

### 4.1 Password hashing

`tests/test_auth_password.py` (new or extend existing):

- `test_new_user_hash_is_argon2` — register a user, fetch hash, assert it starts with `$argon2id$`.
- `test_bcrypt_hash_verifies` — insert a fixture user with a known bcrypt hash, log in, assert success.
- `test_bcrypt_hash_upgrades_on_login` — same fixture, after login fetch hash again, assert it now starts with `$argon2id$`.
- `test_change_password_requires_current` — wrong current_password returns 401.
- `test_change_password_rejects_weak` — `new_password="short"` returns 422.
- `test_change_password_rate_limit` — 6th call within a minute returns 429.

### 4.2 Sanitization

`tests/test_security.py` (new):

- `test_sanitize_strips_script` — `sanitize_user_input("<script>x</script>hi") == "hi"`.
- `test_sanitize_truncates` — input longer than `max_length` is truncated.
- `test_agent_message_sanitized` — POST to `/v3/agent/message` with `<img src=x onerror=alert(1)>foo`, fetch stored message, assert no `<img` substring.

### 4.3 MCP HMAC

`tests/test_mcp_auth.py` (new):

- `test_valid_signature_accepted`.
- `test_missing_signature_401`.
- `test_stale_timestamp_401` — timestamp 400s old.
- `test_tampered_body_401` — sign body A, send body B.
- `test_no_secret_skips_check` — with `MCP_SIGNING_SECRET=""`, requests without signature pass (dev mode).

### 4.4 Org isolation

`tests/test_tenancy.py` (new or extend):

- Create two orgs (A, B), each with a pipeline, a run, a trail, a source.
- `test_user_a_cannot_read_org_b_trail` — log in as A, GET trail belonging to B's run, expect 404.
- `test_user_a_cannot_read_org_b_source` — same for source.
- `test_user_a_cannot_list_org_b_pipelines` — list endpoint returns only A's pipelines.
- `test_superadmin_sees_all_orgs` — `is_admin=True` user lists both A's and B's pipelines and trails.
- `test_system_pipelines_visible_to_all_orgs` — `is_system=TRUE` rows show up for both A and B (preserves current product behavior).

### 4.5 JWT

`tests/test_auth_jwt.py` (new or extend):

- `test_token_without_exp_rejected` — manually mint a token without `exp`, expect 401.
- `test_expired_token_rejected` — token with `exp` in the past, expect 401.

## 5. Rollout

1. Land all backend changes behind a single PR titled `security: argon2 + bleach + mcp-hmac + tenancy fixes`.
2. Land frontend changes (DOMPurify) in a paired PR; merge order doesn't matter (the server-side sanitization is the security boundary; DOMPurify is defense-in-depth against research-content XSS, which is a separate vector).
3. Set `MCP_SIGNING_SECRET` in production secrets before merge — once the env var is set, the server enforces signing. Deploy the MCP client at the same time as the API.
4. Set `FRONTEND_URL` in production env to the actual deployed origin (e.g. `https://app.infobroker.example.com`).
5. Monitor login error rate for 24h post-deploy. Any spike indicates the auto-upgrade path is broken; rollback plan is to revert the `CryptContext` change (bcrypt-only) — the new Argon2id hashes verify fine under the mixed scheme, so rollback is one-way safe.

## 6. Acceptance criteria

- [ ] All new tests in section 4 pass in CI.
- [ ] `rg -n "WHERE\s+\w+\s*=\s*%s" app/routers/v3/ | rg -v "org_id|org_scope_clause"` returns no hits on tenant-scoped tables.
- [ ] `rg -n "dangerouslySetInnerHTML" frontend/src/` shows every match wrapped in `safe(...)`.
- [ ] `rg -n 'allow_origins=\["\*"\]' app/` returns no hits.
- [ ] A manually-minted JWT lacking `exp` is rejected with 401.
- [ ] A new user registered post-deploy has a password hash beginning with `$argon2id$`.
- [ ] An existing user with a bcrypt hash, after one successful login, has a hash beginning with `$argon2id$`.
- [ ] An MCP request without `X-MCP-Signature` when `MCP_SIGNING_SECRET` is set is rejected 401.
- [ ] `pre-pr-gate` skill passes (typecheck + lint + unit + e2e).

## 7. References

- OWASP Password Storage Cheat Sheet (Argon2id parameters).
- RFC 2104 (HMAC).
- Existing webhook signing implementation: `app/services/webhook.py`.
- Existing tenancy helpers: `app/routers/v3/tenancy.py`.
- Audit notes: see commit context for this spec.
