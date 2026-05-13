# Security Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Harden info-broker across password hashing (Argon2id + auto-upgrade), password-change endpoint, input sanitization (server + client), MCP HMAC request signing, org/tenant isolation gaps, and API hardening (CORS, JWT exp, rate limits, Pydantic length caps) per the 2026-05-13 security spec.

**Architecture:** Backend FastAPI ingress sanitizes user-submitted free-text via Pydantic validators; research/scraped content is stored raw and sanitized at render time on the frontend via DOMPurify. Password hashes auto-upgrade from bcrypt to Argon2id on successful login (lazy migration, no script). MCP requests gain HMAC-SHA256 over `timestamp + "." + body` on top of bearer auth, mirroring `app/services/webhook.py`. Org isolation centralizes through `org_scope_clause(user)` in `app/routers/v3/tenancy.py`. JWT decode now requires `exp/iat/sub`.

**Tech Stack:** Python 3.11, FastAPI, psycopg2 (`fetch_one`/`fetch_all`/`execute` helpers in `app/routers/v3/db.py`), `passlib` (`CryptContext`), `argon2-cffi`, `bleach`, `python-jose` (current import: `from jose import jwt`), `slowapi` (`limiter` from `app/lib/rate_limit.py`), Pydantic v2 (`field_validator`, `Field`), React 18 + Vite + Tailwind, DOMPurify 3, pytest.

---

## Task 1 — Argon2id password hashing with bcrypt auto-upgrade

**Files:**
- Modify: `requirements.txt`
- Modify: `app/routers/v3/auth.py`
- Test: `tests/test_auth_password.py` (new)

### Steps

- [ ] **1.1 Add failing test for new-user hash is Argon2id.**

  Create `tests/test_auth_password.py`:

  ```python
  from __future__ import annotations

  from unittest.mock import patch

  from app.routers.v3.auth import _pwd


  def test_new_user_hash_is_argon2():
      h = _pwd.hash("CorrectHorse9!Battery")
      assert h.startswith("$argon2id$"), f"expected argon2id hash, got {h[:20]}"


  def test_bcrypt_hash_still_verifies():
      # known bcrypt hash for "password123"
      bcrypt_hash = "$2b$12$KIXQfPbN8a0wQX8sQ4hQa.UeFvgKZk7Wn/I9DPx5lZv5Z/qB4xRyG"
      # Generate a fresh fixture instead — bcrypt hashes are salt-bound.
      from passlib.hash import bcrypt
      fixture = bcrypt.hash("password123")
      assert _pwd.verify("password123", fixture) is True


  def test_bcrypt_hash_needs_update():
      from passlib.hash import bcrypt
      fixture = bcrypt.hash("password123")
      assert _pwd.needs_update(fixture) is True


  def test_argon2_hash_does_not_need_update():
      h = _pwd.hash("CorrectHorse9!Battery")
      assert _pwd.needs_update(h) is False
  ```

  Run:

  ```bash
  docker compose exec api pytest tests/test_auth_password.py -x -q
  ```

  Expected output: tests fail with `AssertionError` on `test_new_user_hash_is_argon2` (current scheme is bcrypt-only) or import error.

- [ ] **1.2 Add `argon2-cffi` to `requirements.txt`.**

  Append to `requirements.txt`:

  ```
  argon2-cffi>=23.1.0
  ```

  Rebuild the api container so the dep is installed:

  ```bash
  docker compose build api && docker compose up -d api
  ```

  Expected: container starts cleanly, `docker compose exec api python -c "import argon2"` exits 0.

- [ ] **1.3 Replace `_pwd` CryptContext config in `app/routers/v3/auth.py`.**

  Find:

  ```python
  _pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")
  ```

  Replace with:

  ```python
  _pwd = CryptContext(
      schemes=["argon2", "bcrypt"],
      deprecated=["bcrypt"],
      argon2__memory_cost=65536,
      argon2__time_cost=3,
      argon2__parallelism=4,
  )
  ```

  Run:

  ```bash
  docker compose exec api pytest tests/test_auth_password.py -x -q
  ```

  Expected: all four tests pass.

- [ ] **1.4 Add failing test for auto-upgrade on login.**

  Append to `tests/test_auth_password.py`:

  ```python
  def test_bcrypt_hash_upgrades_on_login(monkeypatch):
      from passlib.hash import bcrypt
      from app.routers.v3 import auth as auth_mod

      old_hash = bcrypt.hash("password123")
      user_row = {"id": "uid-1", "username": "u", "password_hash": old_hash, "is_active": True}
      updates: list = []

      def fake_fetch_one(sql, params):
          return dict(user_row)

      def fake_execute(sql, params):
          updates.append((sql, params))

      monkeypatch.setattr(auth_mod, "fetch_one", fake_fetch_one)
      monkeypatch.setattr(auth_mod, "execute", fake_execute)
      # avoid refresh-token DB write
      monkeypatch.setattr(auth_mod, "_make_refresh_token", lambda uid: "rt")
      monkeypatch.setattr(auth_mod, "_make_access_token", lambda uid: "at")

      from app.routers.v3.models import LoginRequest
      auth_mod.login(LoginRequest(username="u", password="password123"))

      assert any("UPDATE ui_users SET password_hash" in sql for sql, _ in updates), updates
      new_hash = updates[0][1][0]
      assert new_hash.startswith("$argon2id$")
  ```

  Run:

  ```bash
  docker compose exec api pytest tests/test_auth_password.py::test_bcrypt_hash_upgrades_on_login -x -q
  ```

  Expected: fails (no UPDATE issued — auto-upgrade not yet wired).

- [ ] **1.5 Wire auto-upgrade in `login()` in `app/routers/v3/auth.py`.**

  Find the existing `login` body:

  ```python
  @router.post("/login", response_model=TokenResponse)
  def login(body: LoginRequest):
      user = fetch_one("SELECT * FROM ui_users WHERE username = %s AND is_active = true", (body.username,))
      if not user or not _pwd.verify(body.password, user["password_hash"]):
          raise HTTPException(status_code=status.[REDACTED:high-entropy-base64:21ch:hash=b136fa43], detail="Invalid credentials")
      return TokenResponse(
         [REDACTED:assigned-token:32ch:hash=7c2643ae](str(user["id"])),
         [REDACTED:assigned-token:34ch:hash=6b28779c](str(user["id"])),
      )
  ```

  Replace with:

  ```python
  @router.post("/login", response_model=TokenResponse)
  def login(body: LoginRequest):
      user = fetch_one("SELECT * FROM ui_users WHERE username = %s AND is_active = true", (body.username,))
      if not user or not _pwd.verify(body.password, user["password_hash"]):
          raise HTTPException(status_code=status.[REDACTED:high-entropy-base64:21ch:hash=b136fa43], detail="Invalid credentials")
      if _pwd.needs_update(user["password_hash"]):
          new_hash = _pwd.hash(body.password)
          execute("UPDATE ui_users SET password_hash = %s WHERE id = %s", (new_hash, user["id"]))
      return TokenResponse(
         [REDACTED:assigned-token:32ch:hash=7c2643ae](str(user["id"])),
         [REDACTED:assigned-token:34ch:hash=6b28779c](str(user["id"])),
      )
  ```

  Run:

  ```bash
  docker compose exec api pytest tests/test_auth_password.py -x -q
  ```

  Expected: all five tests pass.

- [ ] **1.6 Commit.**

  ```bash
  git add requirements.txt app/routers/v3/auth.py tests/test_auth_password.py
  git commit -m "security(auth): Argon2id hashing with bcrypt auto-upgrade on login"
  ```

---

## Task 2 — Password change endpoint `POST /v3/auth/change-password`

**Files:**
- Modify: `app/routers/v3/auth.py`
- Test: `tests/test_auth_password.py`

### Steps

- [ ] **2.1 Add failing tests for change-password endpoint.**

  Append to `tests/test_auth_password.py`:

  ```python
  from fastapi.testclient import TestClient


  def _client_with_user(monkeypatch, user_row, hash_for_password):
      from app.routers.v3 import auth as auth_mod
      from app.main import app
      from passlib.hash import bcrypt  # noqa: F401

      def fake_fetch_one(sql, params):
          if "ui_users WHERE id" in sql:
              return dict(user_row)
          if "ui_users WHERE username" in sql:
              return dict(user_row)
          return None

      updates: list = []

      def fake_execute(sql, params):
          updates.append((sql, params))

      monkeypatch.setattr(auth_mod, "fetch_one", fake_fetch_one)
      monkeypatch.setattr(auth_mod, "execute", fake_execute)
      monkeypatch.setattr(auth_mod, "get_current_user", lambda credentials=None: dict(user_row))
      app.dependency_overrides[auth_mod.get_current_user] = lambda: dict(user_row)
      return TestClient(app), updates


  def test_change_password_rejects_weak(monkeypatch):
      from app.routers.v3.auth import _pwd
      row = {"id": "uid-1", "username": "u", "password_hash": _pwd.hash("OldPassword9!Strong"), "is_active": True}
      client, _ = _client_with_user(monkeypatch, row, "OldPassword9!Strong")
      r = client.post(
          "/v3/auth/change-password",
          json={"current_password": "OldPassword9!Strong", "new_password": "short"},
          headers={"Authorization": "Bearer x"},
      )
      assert r.status_code == 422, r.text


  def test_change_password_wrong_current_returns_401(monkeypatch):
      from app.routers.v3.auth import _pwd
      row = {"id": "uid-1", "username": "u", "password_hash": _pwd.hash("OldPassword9!Strong"), "is_active": True}
      client, _ = _client_with_user(monkeypatch, row, "OldPassword9!Strong")
      r = client.post(
          "/v3/auth/change-password",
          json={"current_password": "WrongCurrent9!", "new_password": "NewPassword9!Strong"},
          headers={"Authorization": "Bearer x"},
      )
      assert r.status_code == 401, r.text


  def test_change_password_rejects_same_as_current(monkeypatch):
      from app.routers.v3.auth import _pwd
      row = {"id": "uid-1", "username": "u", "password_hash": _pwd.hash("OldPassword9!Strong"), "is_active": True}
      client, _ = _client_with_user(monkeypatch, row, "OldPassword9!Strong")
      r = client.post(
          "/v3/auth/change-password",
          json={"current_password": "OldPassword9!Strong", "new_password": "OldPassword9!Strong"},
          headers={"Authorization": "Bearer x"},
      )
      assert r.status_code == 400, r.text


  def test_change_password_success_persists_new_hash(monkeypatch):
      from app.routers.v3.auth import _pwd
      row = {"id": "uid-1", "username": "u", "password_hash": _pwd.hash("OldPassword9!Strong"), "is_active": True}
      client, updates = _client_with_user(monkeypatch, row, "OldPassword9!Strong")
      r = client.post(
          "/v3/auth/change-password",
          json={"current_password": "OldPassword9!Strong", "new_password": "NewPassword9!Strong"},
          headers={"Authorization": "Bearer x"},
      )
      assert r.status_code == 200, r.text
      assert any("UPDATE ui_users SET password_hash" in sql for sql, _ in updates)
      new_hash = updates[-1][1][0]
      assert new_hash.startswith("$argon2id$")
  ```

  Run:

  ```bash
  docker compose exec api pytest tests/test_auth_password.py -x -q
  ```

  Expected: the four new tests fail with 404 (route does not yet exist).

- [ ] **2.2 Add password strength validator and `ChangePasswordIn` model in `app/routers/v3/auth.py`.**

  Add near the top of `app/routers/v3/auth.py`, after the existing imports:

  ```python
  import re

  from fastapi import Request
  from pydantic import BaseModel, field_validator

  from app.lib.rate_limit import limiter


  def [REDACTED:high-entropy-base64:27ch:hash=0d18b29b](v: str) -> str:
      if len(v) < 12:
          raise ValueError("Password must be at least 12 characters")
      if not re.search(r"[\d\W]", v):
          raise ValueError("Password must contain at least one digit or special character")
      return v


  class ChangePasswordIn(BaseModel):
      current_password: str
      new_password: str

      @field_validator("new_password")
      @classmethod
      def _strong(cls, v: str) -> str:
          return [REDACTED:high-entropy-base64:27ch:hash=0d18b29b](v)
  ```

- [ ] **2.3 Add the route handler in `app/routers/v3/auth.py`.**

  Append below the existing `refresh` route:

  ```python
  @router.post("/change-password")
  @limiter.limit("5/minute")
  def change_password(
      request: Request,
      body: ChangePasswordIn,
      user: dict = Depends(get_current_user),
  ) -> dict:
      row = fetch_one("SELECT id, password_hash FROM ui_users WHERE id = %s", (user["id"],))
      if not row or not _pwd.verify(body.current_password, row["password_hash"]):
          raise HTTPException(status_code=status.[REDACTED:high-entropy-base64:21ch:hash=b136fa43], detail="Invalid current password")
      if _pwd.verify(body.new_password, row["password_hash"]):
          raise HTTPException(status_code=400, detail="New password must differ from current")
      new_hash = _pwd.hash(body.new_password)
      execute("UPDATE ui_users SET password_hash = %s WHERE id = %s", (new_hash, user["id"]))
      return {"ok": True}
  ```

  Note: uses `get_current_user` (not `require_analyst_user`) so viewers can also change their own password.

  Run:

  ```bash
  docker compose exec api pytest tests/test_auth_password.py -x -q
  ```

  Expected: all change-password tests pass.

- [ ] **2.4 Add rate-limit test.**

  Append to `tests/test_auth_password.py`:

  ```python
  def test_change_password_rate_limited(monkeypatch):
      from app.routers.v3.auth import _pwd
      row = {"id": "uid-1", "username": "u", "password_hash": _pwd.hash("OldPassword9!Strong"), "is_active": True}
      client, _ = _client_with_user(monkeypatch, row, "OldPassword9!Strong")
      statuses = []
      for _ in range(7):
          r = client.post(
              "/v3/auth/change-password",
              json={"current_password": "OldPassword9!Strong", "new_password": "NewPassword9!Strong"},
              headers={"Authorization": "Bearer x"},
          )
          statuses.append(r.status_code)
      assert 429 in statuses, statuses
  ```

  Run:

  ```bash
  docker compose exec api pytest tests/test_auth_password.py::test_change_password_rate_limited -x -q
  ```

  Expected: passes (`5/minute` cap triggers 429 on the 6th or 7th call).

- [ ] **2.5 Commit.**

  ```bash
  git add app/routers/v3/auth.py tests/test_auth_password.py
  git commit -m "security(auth): add POST /v3/auth/change-password with 5/min rate limit"
  ```

---

## Task 3 — Backend input sanitization (`app/security.py` + Pydantic validators)

**Files:**
- Modify: `requirements.txt`
- Create: `app/security.py`
- Modify: `app/routers/v3/models.py` (AgentMessageIn)
- Modify: `app/routers/v3/pipelines.py` (pipeline create/update model)
- Modify: `app/routers/v3/sources_api.py` (source create/update model)
- Test: `tests/test_security.py` (new)

### Steps

- [ ] **3.1 Add `bleach` to `requirements.txt`.**

  Append:

  ```
  bleach>=6.1.0
  ```

  Rebuild:

  ```bash
  docker compose build api && docker compose up -d api
  ```

  Expected: `docker compose exec api python -c "import bleach"` exits 0.

- [ ] **3.2 Add failing tests for `sanitize_user_input`.**

  Create `tests/test_security.py`:

  ```python
  from __future__ import annotations

  import pytest


  def test_sanitize_strips_script_tag():
      from app.security import sanitize_user_input
      assert sanitize_user_input("<script>x</script>hi") == "hi"


  def test_sanitize_strips_img_onerror():
      from app.security import sanitize_user_input
      out = sanitize_user_input("<img src=x onerror=alert(1)>foo")
      assert "<img" not in out
      assert "onerror" not in out
      assert "foo" in out


  def test_sanitize_truncates_to_max_length():
      from app.security import sanitize_user_input
      out = sanitize_user_input("a" * 9000, max_length=4000)
      assert len(out) == 4000


  def test_sanitize_handles_none():
      from app.security import sanitize_user_input
      assert sanitize_user_input(None) == ""


  def test_sanitize_idempotent():
      from app.security import sanitize_user_input
      once = sanitize_user_input("<b>hello</b>")
      twice = sanitize_user_input(once)
      assert once == twice
  ```

  Run:

  ```bash
  docker compose exec api pytest tests/test_security.py -x -q
  ```

  Expected: fails — `app.security` module does not yet exist.

- [ ] **3.3 Create `app/security.py`.**

  ```python
  """Input sanitization helpers.

  Use sanitize_user_input on user-submitted free-text BEFORE persisting.
  Never apply to scraped HTML, LLM completions, or any research artifact —
  those must be stored raw and sanitized at render time on the frontend.
  """

  from __future__ import annotations

  import bleach

  DEFAULT_MAX_LENGTH = 4000


  def sanitize_user_input(value: str | None, max_length: int = DEFAULT_MAX_LENGTH) -> str:
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

  Run:

  ```bash
  docker compose exec api pytest tests/test_security.py -x -q
  ```

  Expected: all five tests pass.

- [ ] **3.4 Add failing test for `AgentMessageIn` sanitization.**

  Append to `tests/test_security.py`:

  ```python
  def test_agent_message_in_strips_html():
      from app.routers.v3.models import AgentMessageIn
      m = AgentMessageIn(message="<img src=x onerror=alert(1)>hello")
      assert "<img" not in m.message
      assert "hello" in m.message


  def test_agent_message_in_max_length_8000():
      from pydantic import ValidationError
      from app.routers.v3.models import AgentMessageIn
      with pytest.raises(ValidationError):
          AgentMessageIn(message="x" * 8001)
  ```

  Run:

  ```bash
  docker compose exec api pytest tests/test_security.py -x -q
  ```

  Expected: both new tests fail.

- [ ] **3.5 Add validator + length cap to `AgentMessageIn` in `app/routers/v3/models.py`.**

  Find:

  ```python
  class AgentMessageIn(BaseModel):
      message: str
      session_id: str | None = None
      context_job_id: str | None = None
      use_intelligent_search: bool = False
      parent_run_id: str | None = None
  ```

  Replace with:

  ```python
  class AgentMessageIn(BaseModel):
      message: str = Field(..., max_length=8000)
      session_id: str | None = None
      context_job_id: str | None = None
      use_intelligent_search: bool = False
      parent_run_id: str | None = None

      @field_validator("message")
      @classmethod
      def _sanitize_message(cls, v: str) -> str:
          from app.security import sanitize_user_input
          return sanitize_user_input(v, max_length=8000)
  ```

  Ensure the top of `app/routers/v3/models.py` imports:

  ```python
  from pydantic import BaseModel, Field, field_validator
  ```

  (Add `Field` and `field_validator` if not already imported.)

  Run:

  ```bash
  docker compose exec api pytest tests/test_security.py -x -q
  ```

  Expected: all sanitization tests pass.

- [ ] **3.6 Locate pipeline create/update model in `app/routers/v3/pipelines.py`.**

  ```bash
  grep -n "class .*\(In\|Create\|Update\).*BaseModel" /Users/rinehardramos/Projects/info-broker/app/routers/v3/pipelines.py
  ```

  Expected: prints one or more pipeline body models. For each model that has a `name` and/or `description` field, add:

  - `name: str = Field(..., max_length=255)`
  - `description: str | None = Field(None, max_length=4000)`
  - A `@field_validator("name", "description")` that runs `sanitize_user_input` (skipping `None`).

  Pattern to add to each such model:

  ```python
  from app.security import sanitize_user_input
  from pydantic import field_validator

  @field_validator("name")
  @classmethod
  def _sanitize_name(cls, v: str) -> str:
      return sanitize_user_input(v, max_length=255)

  @field_validator("description")
  @classmethod
  def _sanitize_description(cls, v: str | None) -> str | None:
      return sanitize_user_input(v, max_length=4000) if v is not None else None
  ```

- [ ] **3.7 Locate source create/update model in `app/routers/v3/sources_api.py`.**

  ```bash
  grep -n "class .*\(In\|Create\|Update\).*BaseModel" /Users/rinehardramos/Projects/info-broker/app/routers/v3/sources_api.py
  ```

  Apply the same pattern as 3.6 to any model carrying `name` or `description`.

- [ ] **3.8 Run the full test suite to catch regressions.**

  ```bash
  docker compose exec api pytest tests/ -x -q
  ```

  Expected: green. Investigate any failure (likely a test that was sending HTML in a pipeline name as a fixture and expecting it back verbatim — update the fixture, not the validator).

- [ ] **3.9 Commit.**

  ```bash
  git add requirements.txt app/security.py app/routers/v3/models.py app/routers/v3/pipelines.py app/routers/v3/sources_api.py tests/test_security.py
  git commit -m "security: backend sanitize_user_input via bleach + Pydantic validators on user free-text"
  ```

---

## Task 4 — Frontend DOMPurify sanitization

**Files:**
- Modify: `frontend/package.json`
- Create: `frontend/src/lib/sanitize.ts`
- Modify: `frontend/src/components/results/ResultsPanel.tsx`
- Modify: `frontend/src/components/results/ResearchFlow.tsx`
- Modify: `frontend/src/components/live/LiveStream.tsx`
- Modify: `frontend/src/components/agent/AgentChat.tsx` (and any other file with `dangerouslySetInnerHTML`)

### Steps

- [ ] **4.1 Add `dompurify` and types to `frontend/package.json`.**

  In `dependencies`:

  ```json
  "dompurify": "^3.2.0"
  ```

  In `devDependencies`:

  ```json
  "@types/dompurify": "^3.0.5"
  ```

  Install:

  ```bash
  cd /Users/rinehardramos/Projects/info-broker/frontend && npm install
  ```

  Expected: `node_modules/dompurify` exists, `npm ls dompurify` prints version `3.x`.

- [ ] **4.2 Create `frontend/src/lib/sanitize.ts`.**

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

- [ ] **4.3 Enumerate every `dangerouslySetInnerHTML` site.**

  ```bash
  grep -rn "dangerouslySetInnerHTML" /Users/rinehardramos/Projects/info-broker/frontend/src/
  ```

  Expected output: a list of files and line numbers. Record this list; every match must be modified in 4.4.

- [ ] **4.4 Wrap every `__html: <expr>` with `safe(<expr>)`.**

  For each match from 4.3, edit the file:

  Before:

  ```tsx
  <div dangerouslySetInnerHTML={{ __html: rendered }} />
  ```

  After:

  ```tsx
  import { safe } from "@/lib/sanitize";
  // ...
  <div dangerouslySetInnerHTML={{ __html: safe(rendered) }} />
  ```

  Adjust the import path (`@/lib/sanitize` or relative `../../lib/sanitize`) to whatever alias the project uses — check `frontend/tsconfig.json` `paths` and any existing imports in the same file.

  Files known to require this (verify and extend with 4.3 output):
  - `frontend/src/components/results/ResultsPanel.tsx`
  - `frontend/src/components/results/ResearchFlow.tsx`
  - `frontend/src/components/live/LiveStream.tsx`
  - `frontend/src/components/agent/AgentChat.tsx`

- [ ] **4.5 Re-run the grep to confirm zero unwrapped sites remain.**

  ```bash
  grep -rn "dangerouslySetInnerHTML" /Users/rinehardramos/Projects/info-broker/frontend/src/ | grep -v "safe("
  ```

  Expected output: empty (no lines).

- [ ] **4.6 Frontend typecheck + build.**

  ```bash
  cd /Users/rinehardramos/Projects/info-broker/frontend && npm run typecheck && npm run build
  ```

  Expected: zero TS errors, successful Vite build.

- [ ] **4.7 Commit.**

  ```bash
  git add frontend/package.json frontend/package-lock.json frontend/src/lib/sanitize.ts frontend/src/components/results/ResultsPanel.tsx frontend/src/components/results/ResearchFlow.tsx frontend/src/components/live/LiveStream.tsx frontend/src/components/agent/AgentChat.tsx
  git commit -m "security(frontend): DOMPurify sanitize at every dangerouslySetInnerHTML site"
  ```

---

## Task 5 — MCP HMAC-SHA256 request signing

**Files:**
- Create: `app/routers/v3/mcp_auth.py`
- Modify: `mcp_server/client.py`
- Modify: `docker-compose.yml`
- Test: `tests/test_mcp_auth.py` (new)

### Steps

- [ ] **5.1 Read `app/services/webhook.py` to mirror its pattern exactly.**

  ```bash
  sed -n '1,80p' /Users/rinehardramos/Projects/info-broker/app/services/webhook.py
  ```

  Expected: confirm the signing pattern uses `hmac.new(secret.encode(), msg, hashlib.sha256).hexdigest()` and emits an `X-Webhook-Signature: sha256=<hex>` header.

- [ ] **5.2 Add failing tests for `verify_mcp_signature`.**

  Create `tests/test_mcp_auth.py`:

  ```python
  from __future__ import annotations

  import hashlib
  import hmac
  import time

  import pytest
  from fastapi import FastAPI
  from fastapi.testclient import TestClient


  def _sign(secret: str, ts: str, body: bytes) -> str:
      mac = hmac.new(secret.encode("utf-8"), f"{ts}.".encode("utf-8") + body, hashlib.sha256).hexdigest()
      return f"sha256={mac}"


  def _build_app(monkeypatch, secret: str) -> TestClient:
      monkeypatch.setenv("MCP_SIGNING_SECRET", secret)
      import importlib
      from app.routers.v3 import mcp_auth
      importlib.reload(mcp_auth)
      from fastapi import Depends
      app = FastAPI()

      @app.post("/v3/mcp/echo", dependencies=[Depends(mcp_auth.verify_mcp_signature)])
      async def echo(payload: dict) -> dict:
          return payload

      return TestClient(app)


  def test_valid_signature_accepted(monkeypatch):
      client = _build_app(monkeypatch, "test-secret")
      ts = str(int(time.time()))
      body = b'{"hello":"world"}'
      r = client.post(
          "/v3/mcp/echo",
          content=body,
          headers={
              "Content-Type": "application/json",
              "X-MCP-Timestamp": ts,
              "X-MCP-Signature": _sign("test-secret", ts, body),
          },
      )
      assert r.status_code == 200, r.text


  def test_missing_signature_401(monkeypatch):
      client = _build_app(monkeypatch, "test-secret")
      r = client.post("/v3/mcp/echo", json={"hello": "world"})
      assert r.status_code == 401


  def test_stale_timestamp_401(monkeypatch):
      client = _build_app(monkeypatch, "test-secret")
      ts = str(int(time.time()) - 400)
      body = b'{"hello":"world"}'
      r = client.post(
          "/v3/mcp/echo",
          content=body,
          headers={
              "Content-Type": "application/json",
              "X-MCP-Timestamp": ts,
              "X-MCP-Signature": _sign("test-secret", ts, body),
          },
      )
      assert r.status_code == 401


  def test_tampered_body_401(monkeypatch):
      client = _build_app(monkeypatch, "test-secret")
      ts = str(int(time.time()))
      r = client.post(
          "/v3/mcp/echo",
          content=b'{"hello":"tampered"}',
          headers={
              "Content-Type": "application/json",
              "X-MCP-Timestamp": ts,
              "X-MCP-Signature": _sign("test-secret", ts, b'{"hello":"original"}'),
          },
      )
      assert r.status_code == 401


  def test_no_secret_skips_check(monkeypatch):
      client = _build_app(monkeypatch, "")
      r = client.post("/v3/mcp/echo", json={"hello": "world"})
      assert r.status_code == 200
  ```

  Run:

  ```bash
  docker compose exec api pytest tests/test_mcp_auth.py -x -q
  ```

  Expected: import error — `app.routers.v3.mcp_auth` does not exist.

- [ ] **5.3 Create `app/routers/v3/mcp_auth.py`.**

  ```python
  """HMAC-SHA256 verification for MCP requests.

  Mirrors app/services/webhook.py signing pattern. Wraps existing bearer-token
  auth — does not replace it. Bearer identifies the caller; HMAC proves the
  request body is intact and recent.
  """

  from __future__ import annotations

  import hashlib
  import hmac
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

  Run:

  ```bash
  docker compose exec api pytest tests/test_mcp_auth.py -x -q
  ```

  Expected: all five tests pass.

- [ ] **5.4 Add MCP signing helper to `mcp_server/client.py`.**

  Find the existing module-level imports/constants in `mcp_server/client.py` and add (near the top):

  ```python
  import hashlib
  import hmac
  import json
  import os
  import time

  _MCP_SECRET = os.environ.get("MCP_SIGNING_SECRET", "")


  def _sign_request(body: bytes) -> dict[str, str]:
      if not _MCP_SECRET:
          return {}
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

  For every outbound HTTP call in `mcp_server/client.py`, pre-serialize the payload and pass body bytes. Convert:

  ```python
  resp = self._client.post(url, json=payload, headers=headers)
  ```

  To:

  ```python
  body_bytes = json.dumps(payload).encode("utf-8")
  headers = {**headers, "Content-Type": "application/json", **_sign_request(body_bytes)}
  resp = self._client.post(url, content=body_bytes, headers=headers)
  ```

  For GET requests with empty body, pass `b""` to `_sign_request`:

  ```python
  headers = {**headers, **_sign_request(b"")}
  resp = self._client.get(url, headers=headers)
  ```

- [ ] **5.5 Identify MCP-facing routes and apply `verify_mcp_signature` at router level.**

  Inspect routers under `/v3/mcp`:

  ```bash
  grep -rn 'prefix="/v3/mcp\|"/v3/mcp"' /Users/rinehardramos/Projects/info-broker/app/routers/ /Users/rinehardramos/Projects/info-broker/app/main.py
  ```

  - If a router with `prefix="/v3/mcp"` exists, change its constructor:

    ```python
    from app.routers.v3.mcp_auth import verify_mcp_signature
    from fastapi import APIRouter, Depends

    router = APIRouter(prefix="/v3/mcp", tags=["v3-mcp"], dependencies=[Depends(verify_mcp_signature)])
    ```

  - If no `/v3/mcp` FastAPI router exists (MCP is served exclusively by `mcp_server/server.py` FastMCP), document that fact in a comment at the top of `app/routers/v3/mcp_auth.py`:

    ```python
    # NOTE: MCP traffic is served by mcp_server/server.py (FastMCP), not via this
    # FastAPI app. This dependency is exported so a future /v3/mcp/* router can
    # adopt it directly. The client-side signing in mcp_server/client.py is the
    # active enforcement point for now; server-side enforcement happens inside
    # FastMCP middleware (out of scope for this PR).
    ```

    And add a TODO ticket reference in `tasks/todo.md`.

- [ ] **5.6 Add `MCP_SIGNING_SECRET` to `docker-compose.yml`.**

  Under the `api` service environment block and the `mcp_server` service environment block (whichever exist), add:

  ```yaml
  MCP_SIGNING_SECRET: ${MCP_SIGNING_SECRET:-}
  ```

  If `.env.example` exists at the repo root, append:

  ```
  # 32+ byte random hex; generate with: openssl rand -hex 32
  MCP_SIGNING_SECRET=
  ```

- [ ] **5.7 Commit.**

  ```bash
  git add app/routers/v3/mcp_auth.py mcp_server/client.py docker-compose.yml tests/test_mcp_auth.py
  git commit -m "security(mcp): HMAC-SHA256 request signing with 5-minute replay window"
  ```

---

## Task 6 — Org isolation gaps + API hardening (CORS, JWT exp, length caps)

**Files:**
- Modify: `app/routers/v3/tenancy.py` (add `org_scope_clause`)
- Modify: `app/routers/v3/research_api.py` (lines 57, 116, 139)
- Modify: `app/routers/v3/pipelines.py` (lines 330, 366)
- Modify: `app/routers/v3/sources_api.py` (line 264)
- Modify: `app/routers/v3/exports.py` (line 47)
- Modify: `app/routers/v3/auth.py` (JWT decode require + access-token claims)
- Modify: `app/main.py` (CORS allow_headers; no wildcards on credentials)
- Modify: `app/routers/v3/models.py` (Field max_length on `LoginRequest`, `PreferencesIn`, `CoreSettingIn`, `MonitorIn`)
- Test: `tests/test_tenancy.py` (new or extended)
- Test: `tests/test_auth_jwt.py` (new)

### Steps

- [ ] **6.1 Add failing test for `org_scope_clause`.**

  Create `tests/test_tenancy.py` (or append if exists):

  ```python
  from __future__ import annotations


  def test_org_scope_clause_superadmin_empty():
      from app.routers.v3.tenancy import org_scope_clause
      clause, params = org_scope_clause({"id": "u1", "org_id": "o1", "is_admin": True})
      assert clause == ""
      assert params == []


  def test_org_scope_clause_regular_user():
      from app.routers.v3.tenancy import org_scope_clause
      clause, params = org_scope_clause({"id": "u1", "org_id": "o1", "is_admin": False})
      assert clause == "AND org_id = %s"
      assert params == ["o1"]
  ```

  Run:

  ```bash
  docker compose exec api pytest tests/test_tenancy.py -x -q
  ```

  Expected: fails — `org_scope_clause` not defined.

- [ ] **6.2 Add `org_scope_clause` to `app/routers/v3/tenancy.py`.**

  Append to `app/routers/v3/tenancy.py`:

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

  Run:

  ```bash
  docker compose exec api pytest tests/test_tenancy.py -x -q
  ```

  Expected: both tests pass.

- [ ] **6.3 Fix gap at `app/routers/v3/research_api.py:57`.**

  Locate the existing query around line 57. Replace:

  ```python
  fetch_one("SELECT * FROM research_trails WHERE run_id = %s", (run_id,))
  ```

  With:

  ```python
  clause, params = org_scope_clause(user)
  fetch_one(
      f"""
      SELECT rt.*
      FROM research_trails rt
      JOIN pipeline_runs pr ON pr.id = rt.run_id
      WHERE rt.run_id = %s {clause.replace("AND org_id", "AND pr.org_id")}
      """,
      tuple([run_id, *params]),
  )
  ```

  Ensure the route signature includes `user: dict = Depends(get_current_user)` (or an analyst/viewer dependency) and the import for `org_scope_clause`:

  ```python
  from app.routers.v3.tenancy import org_scope_clause
  ```

- [ ] **6.4 Apply identical pattern to `research_api.py:116` and `research_api.py:139`.**

  Both sites read `research_trails` (or join through `pipeline_runs`). Add the same JOIN + `clause.replace("AND org_id", "AND pr.org_id")` pattern. If the query already JOINs `pipeline_runs pr`, just append the un-qualified clause replaced. If it does not JOIN, add the JOIN.

- [ ] **6.5 Fix `app/routers/v3/pipelines.py:330` (pipeline read by id).**

  Replace:

  ```python
  fetch_one("SELECT * FROM pipelines WHERE id = %s", (pipeline_id,))
  ```

  With:

  ```python
  clause, params = org_scope_clause(user)
  fetch_one(
      f"SELECT * FROM pipelines WHERE id = %s {clause}",
      tuple([pipeline_id, *params]),
  )
  ```

- [ ] **6.6 Fix `app/routers/v3/pipelines.py:366` (list pipelines with system rows).**

  Replace:

  ```python
  fetch_all(
      "SELECT * FROM pipelines WHERE user_id = %s OR is_system = TRUE",
      (user_id,),
  )
  ```

  With:

  ```python
  clause, params = org_scope_clause(user)
  fetch_all(
      f"""
      SELECT * FROM pipelines
      WHERE (user_id = %s OR is_system = TRUE)
        AND (TRUE {clause})
      """,
      tuple([user_id, *params]),
  )
  ```

  `is_system = TRUE` rows remain visible to every user/org (current product behavior preserved).

- [ ] **6.7 Fix `app/routers/v3/sources_api.py:264`.**

  Replace:

  ```python
  fetch_one("SELECT * FROM research_sources WHERE id = %s", (source_id,))
  ```

  With:

  ```python
  clause, params = org_scope_clause(user)
  row = fetch_one(
      f"SELECT * FROM research_sources WHERE id = %s {clause}",
      tuple([source_id, *params]),
  )
  if not row:
      raise HTTPException(status_code=404, detail="Source not found")
  ```

  (Returning 404 — not 403 — avoids leaking existence to non-owning orgs.)

- [ ] **6.8 Fix `app/routers/v3/exports.py:47`.**

  Same pattern as 6.3 — `research_trails` JOIN `pipeline_runs pr` with `clause.replace("AND org_id", "AND pr.org_id")`. Ensure the route depends on `get_current_user`.

- [ ] **6.9 Add cross-org isolation test.**

  Append to `tests/test_tenancy.py`:

  ```python
  def test_user_a_cannot_read_org_b_source(monkeypatch):
      from app.routers.v3 import sources_api  # noqa: F401
      # Simulate scope clause behavior at the helper level
      from app.routers.v3.tenancy import org_scope_clause
      user_a = {"id": "ua", "org_id": "org-a", "is_admin": False}
      clause, params = org_scope_clause(user_a)
      sql = f"SELECT * FROM research_sources WHERE id = %s {clause}"
      assert "org_id = %s" in sql
      assert params == ["org-a"]


  def test_superadmin_skips_org_clause():
      from app.routers.v3.tenancy import org_scope_clause
      admin = {"id": "ux", "org_id": "org-x", "is_admin": True}
      clause, params = org_scope_clause(admin)
      assert clause == ""
      assert params == []
  ```

  Run:

  ```bash
  docker compose exec api pytest tests/test_tenancy.py -x -q
  ```

  Expected: passes.

- [ ] **6.10 Regression sweep.**

  ```bash
  cd /Users/rinehardramos/Projects/info-broker && rg -n "WHERE\s+\w+\s*=\s*%s" app/routers/v3/ | rg -v "org_id|org_scope_clause|ui_users|ui_sessions|users WHERE id|user_id"
  ```

  Expected: any remaining hit targeting tenant-scoped tables (`pipelines`, `pipeline_runs`, `research_trails`, `research_sources`, `agent_sessions`, `agent_messages`) must be fixed before proceeding.

- [ ] **6.11 JWT: add `iat` / `org_id` / `is_admin` / `role` to access token; require `exp` on decode.**

  In `app/routers/v3/auth.py`, replace `_make_access_token`:

  ```python
  def _make_access_token(user_id: str) -> str:
      user = fetch_one(
          "SELECT id, org_id, is_admin, role FROM ui_users WHERE id = %s",
          (user_id,),
      ) or {}
      now = datetime.now(timezone.utc)
      payload = {
          "sub": user_id,
          "org_id": str(user.get("org_id") or ""),
          "is_admin": bool(user.get("is_admin")),
          "role": user.get("role") or "analyst",
          "iat": int(now.timestamp()),
          "exp": int((now + timedelta(hours=_ACCESS_HOURS)).timestamp()),
          "type": "access",
      }
      return jwt.encode(payload, _SECRET, algorithm=_ALGO)
  ```

  And replace the `jwt.decode` call in `get_current_user`:

  ```python
  try:
      payload = jwt.decode(
          credentials.credentials,
          _SECRET,
          algorithms=[_ALGO],
          options={"require": ["exp", "iat", "sub"]},
      )
  except JWTError as e:
      raise HTTPException(status_code=status.[REDACTED:high-entropy-base64:21ch:hash=b136fa43], detail=f"Invalid token: {e}")
  ```

  Note: `python-jose` honors `options={"require": [...]}`.

- [ ] **6.12 JWT tests.**

  Create `tests/test_auth_jwt.py`:

  ```python
  from __future__ import annotations

  from datetime import datetime, timedelta, timezone

  import pytest
  from fastapi.security import HTTPAuthorizationCredentials
  from jose import jwt


  def test_token_without_exp_rejected():
      from app.routers.v3.auth import _ALGO, _SECRET, get_current_user
      from fastapi import HTTPException

      token = jwt.encode({"sub": "u1", "type": "access"}, _SECRET, algorithm=_ALGO)
      creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
      with pytest.raises(HTTPException) as exc:
          get_current_user(credentials=creds)
      assert exc.value.status_code == 401


  def test_expired_token_rejected():
      from app.routers.v3.auth import _ALGO, _SECRET, get_current_user
      from fastapi import HTTPException

      past = int((datetime.now(timezone.utc) - timedelta(hours=1)).timestamp())
      token = jwt.encode(
          {"sub": "u1", "iat": past - 10, "exp": past, "type": "access"},
          _SECRET,
          algorithm=_ALGO,
      )
      creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
      with pytest.raises(HTTPException) as exc:
          get_current_user(credentials=creds)
      assert exc.value.status_code == 401
  ```

  Run:

  ```bash
  docker compose exec api pytest tests/test_auth_jwt.py -x -q
  ```

  Expected: both tests pass.

- [ ] **6.13 CORS: tighten `allow_headers` and `allow_methods` in `app/main.py`.**

  Find the existing block:

  ```python
  app.add_middleware(
      CORSMiddleware,
      allow_origins=_CORS_ORIGINS,
      allow_origin_regex=r"https://.*\.ngrok-free\.(app|dev)",
      [REDACTED:high-entropy-base64:22ch:hash=bdeeed6f],
      allow_methods=["*"],
      allow_headers=["*"],
  )
  ```

  Replace `allow_methods` and `allow_headers` with explicit lists:

  ```python
  app.add_middleware(
      CORSMiddleware,
      allow_origins=_CORS_ORIGINS,
      allow_origin_regex=r"https://.*\.ngrok-free\.(app|dev)",
      [REDACTED:high-entropy-base64:22ch:hash=bdeeed6f],
      allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
      allow_headers=["Authorization", "Content-Type", "X-API-Key", "X-MCP-Signature", "X-MCP-Timestamp"],
  )
  ```

  Verify there is no wildcard origin anywhere:

  ```bash
  rg -n 'allow_origins=\["\*"\]' /Users/rinehardramos/Projects/info-broker/app/
  ```

  Expected: no hits.

- [ ] **6.14 Pydantic length caps on remaining user-facing models in `app/routers/v3/models.py`.**

  Apply `Field(..., max_length=N)`:

  - `LoginRequest.username`: `max_length=255`
  - `LoginRequest.password`: `max_length=1024` (must allow long valid passwords; no validator sanitization on credentials)
  - `PreferencesIn` string fields: `max_length=4000`
  - `CoreSettingIn` string fields: `max_length=4000`
  - `MonitorIn` string fields: `max_length=4000`

  Concrete change for `LoginRequest`:

  ```python
  class LoginRequest(BaseModel):
      username: str = Field(..., max_length=255)
      password: str = Field(..., max_length=1024)
  ```

  Run the test suite:

  ```bash
  docker compose exec api pytest tests/ -x -q
  ```

  Expected: all green.

- [ ] **6.15 Final acceptance sweeps.**

  Run all four spec acceptance commands:

  ```bash
  cd /Users/rinehardramos/Projects/info-broker
  rg -n "WHERE\s+\w+\s*=\s*%s" app/routers/v3/ | rg -v "org_id|org_scope_clause|ui_users|ui_sessions"
  rg -n "dangerouslySetInnerHTML" frontend/src/ | rg -v "safe\("
  rg -n 'allow_origins=\["\*"\]' app/
  docker compose exec api pytest tests/ -x -q
  ```

  Expected for each:
  1. No hits on tenant-scoped tables.
  2. No unwrapped `dangerouslySetInnerHTML` sites.
  3. No wildcard CORS origins.
  4. All tests pass.

- [ ] **6.16 Commit and push.**

  ```bash
  git add app/routers/v3/tenancy.py app/routers/v3/research_api.py app/routers/v3/pipelines.py app/routers/v3/sources_api.py app/routers/v3/exports.py app/routers/v3/auth.py app/routers/v3/models.py app/main.py tests/test_tenancy.py tests/test_auth_jwt.py
  git commit -m "security: org_scope_clause + isolation gap fixes, JWT exp required, CORS lockdown, length caps"
  ```

  Then run pre-PR gate before pushing:

  ```bash
  cd /Users/rinehardramos/Projects/info-broker && docker compose exec api pytest tests/ -x -q && cd frontend && npm run typecheck && npm run build
  ```

  Expected: all green. Then `git push` and monitor pipeline.
