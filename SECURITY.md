# Security & Supply-Chain Policy

This document covers the runtime security model (Phase 6) and the
supply-chain hardening workflow.

## Runtime hardening (Phase 6)

All untrusted data flows through `security.py`:

| Vector | Mitigation |
|---|---|
| SSRF (`scrape_url`, Apify fetch) | `safe_fetch_url` — http(s) only, DNS-time block of loopback / RFC1918 / link-local / metadata IPs, redirects disabled, body cap, optional Content-Type allow-list |
| Prompt injection | `sanitize_for_prompt` wraps untrusted text in `<<<BEGIN_…>>>` / `<<<END_…>>>` fences; system prompt instructs the model to treat fenced content as data |
| CSV / XLSX formula injection | `escape_dataframe_cells` prepends `'` to any cell starting with `= + - @ \t \r` |
| PostgreSQL `\x00` rejection | `coerce_db_text` / `scrub_jsonb` strip NUL bytes and cap field length |
| SQL identifier injection | All queries are parameterized; any future dynamic identifier MUST pass `is_safe_sql_identifier` |
| String-built SQL queries | **Two-layer enforcement**: ruff `S608` at lint time + `test_no_sql_string_formatting.py` AST scan in pytest. Forbids f-strings, `.format()`, `%`, and `+` interpolation as the first arg of any `execute` / `executemany` / `read_sql*` call. Cannot be silenced with `# noqa` — the test always runs in CI. Devs **must** pass values as parameters: `cur.execute("... WHERE id = %s", (var,))`. |
| LLM-driven search abuse | `validate_search_query` strips control chars, collapses whitespace, caps length |
| CLI input → DB | `interactive_grading` runs feedback through `coerce_db_text` before INSERT |

Tests: `python3 -m pytest test_security.py -v` (60 unit, 4 integration).

## Supply-chain hardening

The project uses **[`uv`](https://github.com/astral-sh/uv)** as its
package manager. `uv` provides:

- Fully resolved, **hash-pinned `uv.lock`** (PEP 691 hashes per file).
- Refuses to install if a downloaded artifact's hash doesn't match the lock.
- Reproducible builds across machines.
- Built-in audit against the PyPA advisory database.

### Day-to-day workflow

```sh
# One-time install of uv itself (verify the installer signature first):
curl -LsSf https://astral.sh/uv/install.sh | sh

# Sync the environment from the lockfile (refuses on hash mismatch):
uv sync --frozen

# Add a new dependency and re-lock:
uv add some-package
uv lock

# Bump everything to the latest compatible versions:
uv lock --upgrade

# Audit the resolved set against PyPA advisories:
uv pip audit
```

### CI gates (recommended)

1. `uv sync --frozen` — fail if `uv.lock` is out of date.
2. `uv pip audit --strict` — fail on any known CVE.
3. `python3 -m pytest test_security.py` — fail on any Phase 6 regression.

### Why not bare `pip install -r requirements.txt`?

`requirements.txt` is kept as a fully-pinned fallback, but it does **not**
carry per-file hashes. An attacker who compromises a mirror or performs
a dependency-confusion swap could ship a malicious wheel under a
matching version string and `pip` would happily install it. With `uv`'s
hash-pinned lock, the install is rejected.

If you must use `pip`, generate a hash-pinned file and use it:

```sh
uv export --format requirements-txt --hashes > requirements.lock
pip install --require-hashes -r requirements.lock
```

### Index hardening

`pyproject.toml` sets `tool.uv.index-strategy = "first-index"` so `uv`
will not silently fall back to a secondary index. This blocks the
classic dependency-confusion attack where an internal package name is
also registered on public PyPI.

### Reporting

Security issues: open a private advisory on the project repo. Do not
file public issues for unpatched vulnerabilities.
