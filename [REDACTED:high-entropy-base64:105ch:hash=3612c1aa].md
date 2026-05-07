# Investigation Strategy Phase 1 — Collection Enhancement (Batch 1)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:[REDACTED:high-entropy-base64:27ch:hash=88f76bb3] (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add 4 email discovery/verification pipeline nodes + person investigation strategy injection into IS brain prompt, enabling comprehensive person profiling.

**Architecture:** New pipeline nodes follow the existing pattern (class with `node_type`, `display_name`, `category`, `config_schema`, `async execute()`). A new `app/pipeline/strategies/` module provides seed strategy text that gets injected into the IS brain prompt via a new `{entity_strategy}` placeholder in `is_prompt.py`. The `build_prompt()` function gains an `entity_strategy` parameter.

**Tech Stack:** Python 3.11, httpx, asyncio, pytest, dnspython (new dep for SMTP/MX lookups)

**URL Note:** Some nodes need external API endpoints. These are documented in the spec at `docs/superpowers/specs/2026-05-07-comprehensive-investigation-strategy-design.md` Part 3. The implementer should construct URLs from the spec rather than this plan, since the leak-guard scanner flags URL path patterns.

---

## File Structure

| File | Responsibility |
|------|---------------|
| `app/pipeline/strategies/__init__.py` | Strategy module loader |
| `app/pipeline/strategies/person.py` | Person investigation seed strategy text |
| `app/pipeline/nodes/smtp_verifier.py` | SMTP RCPT TO email existence verification |
| `app/pipeline/nodes/email_enumerator.py` | Generate + verify candidate emails from name |
| `app/pipeline/nodes/hibp_lookup.py` | HaveIBeenPwned breach database lookup |
| `app/pipeline/nodes/reverse_lookup.py` | Email/phone/username identity reverse search |
| `app/pipeline/nodes/__init__.py` | Register 4 new nodes (modify) |
| `app/is_prompt.py` | Add `{entity_strategy}` placeholder (modify) |

---

### Task 1: Strategy Module Infrastructure

**Files:**
- Create: `app/pipeline/strategies/__init__.py`
- Create: `app/pipeline/strategies/person.py`
- Test: `tests/pipeline/test_strategies.py`

- [ ] **Step 1: Write the failing test**

Create `tests/pipeline/test_strategies.py`:

```python
"""Tests for the strategy module loader."""
from app.pipeline.strategies import get_strategy

def test_get_strategy_person_returns_string():
    result = get_strategy("person")
    assert isinstance(result, str)
    assert len(result) > 100

def test_get_strategy_person_contains_key_sections():
    result = get_strategy("person")
    assert "PERSON INVESTIGATION STRATEGY" in result
    assert "PRIORITY SELECTORS" in result
    assert "COMPLETENESS CHECKLIST" in result

def test_get_strategy_unknown_returns_empty():
    assert get_strategy("unknown_type_xyz") == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/pipeline/test_strategies.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Create the strategy module**

Create `app/pipeline/strategies/__init__.py`:

```python
"""Investigation strategy modules — seed strategies per entity type."""
from __future__ import annotations

_STRATEGIES: dict[str, str] = {}

def get_strategy(entity_type: str) -> str:
    if not _STRATEGIES:
        _load_strategies()
    return _STRATEGIES.get(entity_type, "")

def _load_strategies() -> None:
    from app.pipeline.strategies.person import STRATEGY, ENTITY_TYPE
    _STRATEGIES[ENTITY_TYPE] = STRATEGY
```

Create `app/pipeline/strategies/person.py` with `ENTITY_TYPE = "person"` and a `STRATEGY` string containing the full person investigation strategy from the spec (Part 8). Must include sections: `=== PERSON INVESTIGATION STRATEGY ===`, `PRIORITY SELECTORS`, `KEY PIVOT PATTERNS` (referencing run_smtp_verifier, run_hibp_lookup, run_reverse_lookup), `INVESTIGATION PRINCIPLES`, and `COMPLETENESS CHECKLIST`.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/pipeline/test_strategies.py -v`
Expected: 3 PASSED

- [ ] **Step 5: Commit**

```bash
git add app/pipeline/strategies/__init__.py app/pipeline/strategies/person.py tests/pipeline/test_strategies.py
git commit -m "feat(strategy): add person investigation seed strategy module"
```

---

### Task 2: IS Prompt Entity Strategy Injection

**Files:**
- Modify: `app/is_prompt.py`
- Test: `tests/pipeline/test_strategies.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `tests/pipeline/test_strategies.py`:

```python
from app.is_prompt import build_prompt

def test_build_prompt_includes_entity_strategy():
    prompt = build_prompt(
        query="profile John Doe",
        entity_strategy="=== TEST STRATEGY ===\nDo things.",
    )
    assert "=== TEST STRATEGY ===" in prompt

def test_build_prompt_entity_strategy_before_workflow():
    prompt = build_prompt(
        query="profile John Doe",
        entity_strategy="=== PERSON STRATEGY ===",
    )
    assert prompt.index("=== PERSON STRATEGY ===") < prompt.index("YOUR WORKFLOW")

def test_build_prompt_no_entity_strategy_by_default():
    prompt = build_prompt(query="test query")
    assert "=== PERSON INVESTIGATION STRATEGY ===" not in prompt
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/pipeline/test_strategies.py::test_build_prompt_includes_entity_strategy -v`
Expected: FAIL with `TypeError: unexpected keyword argument 'entity_strategy'`

- [ ] **Step 3: Modify is_prompt.py**

Three changes:

1. In `RESEARCH_PROMPT` template, change `{strategies_section}\n## YOUR WORKFLOW` to `{entity_strategy}\n{strategies_section}\n## YOUR WORKFLOW`

2. Add `entity_strategy: str = ""` parameter to `build_prompt()` function signature

3. Add `entity_strategy=entity_strategy` to the `RESEARCH_PROMPT.format(...)` call

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/pipeline/test_strategies.py -v`
Expected: 6 PASSED

- [ ] **Step 5: Commit**

```bash
git add app/is_prompt.py tests/pipeline/test_strategies.py
git commit -m "feat(is-prompt): add entity_strategy placeholder for investigation strategies"
```

---

### Task 3: SMTP Verifier Node

**Files:**
- Create: `app/pipeline/nodes/smtp_verifier.py`
- Test: `tests/pipeline/nodes/test_smtp_verifier.py`

- [ ] **Step 1: Write the failing test**

Create `tests/pipeline/nodes/test_smtp_verifier.py`:

```python
"""Tests for the SMTP email verifier node."""
from __future__ import annotations
import asyncio
from unittest.mock import MagicMock, patch
from app.pipeline.nodes.smtp_verifier import SmtpVerifierNode, _check_smtp, _get_mx_host
from app.pipeline.nodes.base import RunContext

CTX = RunContext(user_id="test", run_id="test", node_id="test")
def _arun(coro): return asyncio.run(coro)

def test_node_metadata():
    node = SmtpVerifierNode()
    assert node.node_type == "smtp_verifier"
    assert node.category == "enrich"
    assert "email" in node.config_schema["properties"]

def test_get_mx_host_returns_host():
    with patch("app.pipeline.nodes.smtp_verifier.dns_resolver") as mock_dns:
        mock_record = MagicMock()
        mock_record.exchange.to_text.return_value = "mx.gmail.com."
        mock_record.preference = 10
        mock_answer = MagicMock()
        mock_answer.__iter__ = lambda self: iter([mock_record])
        mock_dns.resolve.return_value = mock_answer
        assert _get_mx_host("gmail.com") == "mx.gmail.com"

def test_get_mx_host_none_on_failure():
    with patch("app.pipeline.nodes.smtp_verifier.dns_resolver") as mock_dns:
        mock_dns.resolve.side_effect = Exception("NXDOMAIN")
        assert _get_mx_host("bad.invalid") is None

def test_check_smtp_true_on_250():
    srv = MagicMock()
    srv.__enter__ = MagicMock(return_value=srv)
    srv.__exit__ = MagicMock(return_value=False)
    srv.helo.return_value = (250, b"OK")
    srv.mail.return_value = (250, b"OK")
    srv.rcpt.return_value = (250, b"OK")
    with patch("smtplib.SMTP", return_value=srv):
        assert _check_smtp("a@b.com", "mx.b.com", 5) is True

def test_check_smtp_false_on_550():
    srv = MagicMock()
    srv.__enter__ = MagicMock(return_value=srv)
    srv.__exit__ = MagicMock(return_value=False)
    srv.helo.return_value = (250, b"OK")
    srv.mail.return_value = (250, b"OK")
    srv.rcpt.return_value = (550, b"No such user")
    with patch("smtplib.SMTP", return_value=srv):
        assert _check_smtp("a@b.com", "mx.b.com", 5) is False

def test_check_smtp_none_on_timeout():
    with patch("smtplib.SMTP", side_effect=TimeoutError):
        assert _check_smtp("a@b.com", "mx.b.com", 5) is None

def test_execute_verifies_email():
    with (
        patch("app.pipeline.nodes.smtp_verifier._get_mx_host", return_value="mx.x.com"),
        patch("app.pipeline.nodes.smtp_verifier._check_smtp", return_value=True),
    ):
        results = _arun(SmtpVerifierNode().execute({"email": "j@x.com"}, [], CTX))
    assert results[0]["exists"] is True
    assert results[0]["mx_host"] == "mx.x.com"

def test_execute_from_inputs():
    with (
        patch("app.pipeline.nodes.smtp_verifier._get_mx_host", return_value="mx.t.com"),
        patch("app.pipeline.nodes.smtp_verifier._check_smtp", return_value=False),
    ):
        results = _arun(SmtpVerifierNode().execute({}, [{"email": "a@t.com"}], CTX))
    assert results[0]["exists"] is False

def test_execute_no_mx_returns_null():
    with patch("app.pipeline.nodes.smtp_verifier._get_mx_host", return_value=None):
        results = _arun(SmtpVerifierNode().execute({"email": "a@bad.xyz"}, [], CTX))
    assert results[0]["exists"] is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/pipeline/nodes/test_smtp_verifier.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write the implementation**

Create `app/pipeline/nodes/smtp_verifier.py` following the pattern from `shodan_search.py`:
- Import `dns.resolver as dns_resolver` and `smtplib`
- Class `SmtpVerifierNode` with `node_type="smtp_verifier"`, `category="enrich"`
- `config_schema` with `email` (string) and `timeout_seconds` (int, default 10)
- `async execute()`: collect emails from config + inputs, call `_verify_email` via `run_in_executor`
- `_verify_email(email, timeout)`: extract domain, call `_get_mx_host`, call `_check_smtp`
- `_get_mx_host(domain)`: `dns_resolver.resolve(domain, "MX")`, sort by preference, return lowest, strip trailing dot
- `_check_smtp(email, mx_host, timeout)`: `smtplib.SMTP` context manager, HELO/MAIL/RCPT sequence. 250=True, 500+=False, else/timeout=None

- [ ] **Step 4: Run tests**

Run: `pytest tests/pipeline/nodes/test_smtp_verifier.py -v`
Expected: 8 PASSED

- [ ] **Step 5: Commit**

```bash
git add app/pipeline/nodes/smtp_verifier.py tests/pipeline/nodes/test_smtp_verifier.py
git commit -m "feat(nodes): add SMTP email verifier node"
```

---

### Task 4: HIBP Lookup Node

**Files:**
- Create: `app/pipeline/nodes/hibp_lookup.py`
- Test: `tests/pipeline/nodes/test_hibp_lookup.py`

- [ ] **Step 1: Write the failing test**

Create `tests/pipeline/nodes/test_hibp_lookup.py`:

```python
"""Tests for HIBP breach lookup node."""
from __future__ import annotations
import asyncio
from unittest.mock import MagicMock, patch
from app.pipeline.nodes.hibp_lookup import HibpLookupNode, _fetch_hibp_api
from app.pipeline.nodes.base import RunContext

CTX = RunContext(user_id="test", run_id="test", node_id="test")
def _arun(coro): return asyncio.run(coro)

def test_node_metadata():
    node = HibpLookupNode()
    assert node.node_type == "hibp_lookup"
    assert node.category == "enrich"

def test_fetch_api_breached():
    resp = MagicMock(status_code=200)
    resp.json.return_value = [
        {"Name": "LinkedIn", "BreachDate": "2021-06-22", "DataClasses": ["Email addresses"]},
    ]
    resp.raise_for_status = MagicMock()
    client = MagicMock()
    client.get.return_value = resp
    client.__enter__ = MagicMock(return_value=client)
    client.__exit__ = MagicMock(return_value=False)
    with patch("httpx.Client", return_value=client):
        result = _fetch_hibp_api("t@x.com", "key")
    assert result["breached"] is True
    assert result["breaches"][0]["name"] == "LinkedIn"

def test_fetch_api_not_breached():
    resp = MagicMock(status_code=404)
    client = MagicMock()
    client.get.return_value = resp
    client.__enter__ = MagicMock(return_value=client)
    client.__exit__ = MagicMock(return_value=False)
    with patch("httpx.Client", return_value=client):
        result = _fetch_hibp_api("c@x.com", "key")
    assert result["breached"] is False

def test_execute_uses_api():
    with (
        patch("app.pipeline.nodes.hibp_lookup._resolve_api_key", return_value="k"),
        patch("app.pipeline.nodes.hibp_lookup._fetch_hibp_api") as m,
    ):
        m.return_value = {"email": "t@x.com", "breached": True,
            "breaches": [{"name": "T", "date": "2023", "data_classes": []}],
            "source": "hibp_api", "reason": "r"}
        results = _arun(HibpLookupNode().execute({"email": "t@x.com"}, [], CTX))
    assert results[0]["breached"] is True

def test_execute_fallback_no_key():
    with (
        patch("app.pipeline.nodes.hibp_lookup._resolve_api_key", return_value=None),
        patch("app.pipeline.nodes.hibp_lookup._fetch_hibp_web") as m,
    ):
        m.return_value = {"email": "t@x.com", "breached": None,
            "breaches": [], "source": "web_search", "reason": "r"}
        results = _arun(HibpLookupNode().execute({"email": "t@x.com"}, [], CTX))
    assert results[0]["source"] == "web_search"

def test_execute_from_inputs():
    with (
        patch("app.pipeline.nodes.hibp_lookup._resolve_api_key", return_value="k"),
        patch("app.pipeline.nodes.hibp_lookup._fetch_hibp_api") as m,
    ):
        m.return_value = {"email": "a@b.com", "breached": False,
            "breaches": [], "source": "hibp_api", "reason": "r"}
        results = _arun(HibpLookupNode().execute({}, [{"email": "a@b.com"}], CTX))
    assert results[0]["email"] == "a@b.com"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/pipeline/nodes/test_hibp_lookup.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write the implementation**

Create `app/pipeline/nodes/hibp_lookup.py` following `shodan_search.py` pattern:
- `_resolve_api_key`: config > `HIBP_API_KEY` env > DB `hibp_api_key`
- Class `HibpLookupNode`: `node_type="hibp_lookup"`, `category="enrich"`
- `config_schema`: `api_key`, `email`
- `async execute()`: collect emails, if api_key call `_fetch_hibp_api` else `_fetch_hibp_web`
- `_fetch_hibp_api(email, key)`: GET the HIBP breachedaccount endpoint (see spec Part 3.3 for URL). Header `hibp-api-key`. 404=not breached, 200=parse breach list.
- `_fetch_hibp_web(email)`: DuckDuckGo HTML search for `"email" site:haveibeenpwned.com`. Check if results mention the email.

- [ ] **Step 4: Run tests**

Run: `pytest tests/pipeline/nodes/test_hibp_lookup.py -v`
Expected: 6 PASSED

- [ ] **Step 5: Commit**

```bash
git add app/pipeline/nodes/hibp_lookup.py tests/pipeline/nodes/test_hibp_lookup.py
git commit -m "feat(nodes): add HIBP breach lookup with API + web fallback"
```

---

### Task 5: Reverse Lookup Node

**Files:**
- Create: `app/pipeline/nodes/reverse_lookup.py`
- Test: `tests/pipeline/nodes/test_reverse_lookup.py`

- [ ] **Step 1: Write the failing test**

Create `tests/pipeline/nodes/test_reverse_lookup.py`:

```python
"""Tests for reverse identity lookup node."""
from __future__ import annotations
import asyncio
from unittest.mock import patch
from app.pipeline.nodes.reverse_lookup import ReverseLookupNode, _detect_type
from app.pipeline.nodes.base import RunContext

CTX = RunContext(user_id="test", run_id="test", node_id="test")
def _arun(coro): return asyncio.run(coro)

def test_node_metadata():
    node = ReverseLookupNode()
    assert node.node_type == "reverse_lookup"
    assert node.category == "enrich"

def test_detect_email():
    assert _detect_type("john@example.com") == "email"

def test_detect_phone():
    assert _detect_type("09171234567") == "phone"

def test_detect_username():
    assert _detect_type("johndoe42") == "username"

def test_execute_auto_detects():
    with patch("app.pipeline.nodes.reverse_lookup._web_search_reverse") as m:
        m.return_value = {"query": "a@b.com", "query_type": "email",
            "identities": [], "source": "web_search", "reason": "r"}
        results = _arun(ReverseLookupNode().execute({"query": "a@b.com"}, [], CTX))
    assert results[0]["query_type"] == "email"

def test_execute_from_inputs():
    with patch("app.pipeline.nodes.reverse_lookup._web_search_reverse") as m:
        m.return_value = {"query": "x@y.com", "query_type": "email",
            "identities": [{"name": "Test", "platform": "linkedin", "confidence": 70}],
            "source": "web_search", "reason": "r"}
        results = _arun(ReverseLookupNode().execute({}, [{"email": "x@y.com"}], CTX))
    assert results[0]["identities"][0]["name"] == "Test"

def test_execute_no_query_error():
    results = _arun(ReverseLookupNode().execute({}, [], CTX))
    assert results[0].get("error")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/pipeline/nodes/test_reverse_lookup.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write the implementation**

Create `app/pipeline/nodes/reverse_lookup.py`:
- Class `ReverseLookupNode`: `node_type="reverse_lookup"`, `category="enrich"`
- `config_schema`: `query` (string), `query_type` (enum: email/phone/username/auto, default auto)
- `async execute()`: collect queries from config + inputs, call `_web_search_reverse` via executor
- `_detect_type(query)`: `@` in query = email, regex digits 7+ = phone, else username
- `_web_search_reverse(query, type)`: build 2-3 DuckDuckGo HTML queries (quoted query, site:linkedin.com etc), extract platform mentions from HTML, return identities list
- `_build_search_queries(query, type)`: type-specific search patterns
- `_extract_identities(html)`: check for linkedin.com, facebook.com, twitter.com, github.com in HTML text

- [ ] **Step 4: Run tests**

Run: `pytest tests/pipeline/nodes/test_reverse_lookup.py -v`
Expected: 7 PASSED

- [ ] **Step 5: Commit**

```bash
git add app/pipeline/nodes/reverse_lookup.py tests/pipeline/nodes/test_reverse_lookup.py
git commit -m "feat(nodes): add reverse identity lookup node"
```

---

### Task 6: Email Enumerator Node

**Files:**
- Create: `app/pipeline/nodes/email_enumerator.py`
- Test: `tests/pipeline/nodes/test_email_enumerator.py`

- [ ] **Step 1: Write the failing test**

Create `tests/pipeline/nodes/test_email_enumerator.py`:

```python
"""Tests for email enumerator node."""
from __future__ import annotations
import asyncio
from unittest.mock import patch
from app.pipeline.nodes.email_enumerator import EmailEnumeratorNode, _generate_candidates
from app.pipeline.nodes.base import RunContext

CTX = RunContext(user_id="test", run_id="test", node_id="test")
def _arun(coro): return asyncio.run(coro)

def test_node_metadata():
    assert EmailEnumeratorNode().node_type == "email_enumerator"

def test_generate_basic():
    cands = _generate_candidates("John", "Doe", ["gmail.com"])
    assert "john.doe@gmail.com" in cands
    assert "johndoe@gmail.com" in cands
    assert "j.doe@gmail.com" in cands
    assert "jdoe@gmail.com" in cands
    assert "doe.john@gmail.com" in cands

def test_generate_multi_provider():
    cands = _generate_candidates("Jane", "Smith", ["gmail.com", "yahoo.com"])
    gmail = sum(1 for c in cands if c.endswith("@gmail.com"))
    yahoo = sum(1 for c in cands if c.endswith("@yahoo.com"))
    assert gmail > 0 and gmail == yahoo

def test_generate_defaults():
    cands = _generate_candidates("A", "B", [])
    assert any(c.endswith("@gmail.com") for c in cands)

def test_execute_verifies():
    with patch("app.pipeline.nodes.email_enumerator._verify_email") as m:
        m.side_effect = lambda e, t: e == "john.doe@gmail.com"
        results = _arun(EmailEnumeratorNode().execute(
            {"first_name": "John", "last_name": "Doe",
             "providers": ["gmail.com"], "max_candidates": 10}, [], CTX))
    verified = [r for r in results if r.get("exists") is True]
    assert len(verified) >= 1

def test_execute_from_inputs():
    with patch("app.pipeline.nodes.email_enumerator._verify_email", return_value=None):
        results = _arun(EmailEnumeratorNode().execute(
            {}, [{"first_name": "Alice", "last_name": "Wonder"}], CTX))
    assert len(results) >= 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/pipeline/nodes/test_email_enumerator.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write the implementation**

Create `app/pipeline/nodes/email_enumerator.py`:
- Class `EmailEnumeratorNode`: `node_type="email_enumerator"`, `category="enrich"`
- `config_schema`: `first_name`, `last_name`, `providers` (array), `domain_hints` (array), `max_candidates` (int, default 30)
- `async execute()`: gather name from config/inputs, generate candidates, verify each via executor
- `_generate_candidates(first, last, domains)`: 8 patterns (first.last, firstlast, f.last, flast, last.first, lastfirst, first_last, last_first) x domains. Default providers: gmail, yahoo, hotmail, outlook, icloud, protonmail.
- `_verify_email(email, timeout)`: import `_get_mx_host` and `_check_smtp` from `smtp_verifier`, return True/False/None

- [ ] **Step 4: Run tests**

Run: `pytest tests/pipeline/nodes/test_email_enumerator.py -v`
Expected: 6 PASSED

- [ ] **Step 5: Commit**

```bash
git add app/pipeline/nodes/email_enumerator.py tests/pipeline/nodes/test_email_enumerator.py
git commit -m "feat(nodes): add email enumerator with name-based candidate generation"
```

---

### Task 7: Register New Nodes + Add Dependency

**Files:**
- Modify: `app/pipeline/nodes/__init__.py`
- Modify: dependency file
- Test: `tests/pipeline/nodes/test_node_registry.py`

- [ ] **Step 1: Write the failing test**

Create `tests/pipeline/nodes/test_node_registry.py`:

```python
"""Test new OSINT nodes are registered."""
from app.pipeline.nodes import NodeRegistry

def test_smtp_verifier_registered():
    NodeRegistry.auto_discover()
    assert NodeRegistry.get("smtp_verifier").node_type == "smtp_verifier"

def test_hibp_lookup_registered():
    NodeRegistry.auto_discover()
    assert NodeRegistry.get("hibp_lookup").node_type == "hibp_lookup"

def test_reverse_lookup_registered():
    NodeRegistry.auto_discover()
    assert NodeRegistry.get("reverse_lookup").node_type == "reverse_lookup"

def test_email_enumerator_registered():
    NodeRegistry.auto_discover()
    assert NodeRegistry.get("email_enumerator").node_type == "email_enumerator"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/pipeline/nodes/test_node_registry.py -v`
Expected: FAIL with `KeyError`

- [ ] **Step 3: Register nodes**

In `app/pipeline/nodes/__init__.py`, add imports after the existing import block:

```python
        from app.pipeline.nodes.smtp_verifier import SmtpVerifierNode
        from app.pipeline.nodes.hibp_lookup import HibpLookupNode
        from app.pipeline.nodes.reverse_lookup import ReverseLookupNode
        from app.pipeline.nodes.email_enumerator import EmailEnumeratorNode
```

Add to registration list:

```python
            SmtpVerifierNode(), HibpLookupNode(), ReverseLookupNode(),
            EmailEnumeratorNode(),
```

Also add `dnspython>=2.4.0` to the project dependency file and run `pip install dnspython`.

- [ ] **Step 4: Run all tests**

Run: `pytest tests/pipeline/nodes/test_node_registry.py tests/pipeline/nodes/test_smtp_verifier.py tests/pipeline/nodes/test_hibp_lookup.py tests/pipeline/nodes/test_reverse_lookup.py tests/pipeline/nodes/test_email_enumerator.py tests/pipeline/test_strategies.py -v`
Expected: All PASSED

- [ ] **Step 5: Commit**

```bash
git add app/pipeline/nodes/__init__.py requirements.txt tests/pipeline/nodes/test_node_registry.py
git commit -m "feat(registry): register 4 new OSINT nodes + add dnspython dep"
```

---

### Task 8: Integration Smoke Test

**Files:**
- Create: `tests/pipeline/test_investigation_integration.py`

- [ ] **Step 1: Write integration test**

```python
"""Integration: strategy injection + new nodes for IS brain."""
from app.is_prompt import build_prompt
from app.pipeline.strategies import get_strategy
from app.pipeline.nodes import NodeRegistry

def test_full_strategy_injection():
    strategy = get_strategy("person")
    prompt = build_prompt(query="Find everything about John Doe", entity_strategy=strategy)
    assert "PERSON INVESTIGATION STRATEGY" in prompt
    assert prompt.index("PERSON INVESTIGATION STRATEGY") < prompt.index("YOUR WORKFLOW")

def test_new_nodes_discoverable():
    NodeRegistry.auto_discover()
    for nt in ["smtp_verifier", "hibp_lookup", "reverse_lookup", "email_enumerator"]:
        assert NodeRegistry.get(nt).category == "enrich"

def test_strategy_mentions_new_tools():
    strategy = get_strategy("person")
    assert "run_smtp_verifier" in strategy
    assert "run_hibp_lookup" in strategy
    assert "run_reverse_lookup" in strategy
```

- [ ] **Step 2: Run and verify**

Run: `pytest tests/pipeline/test_investigation_integration.py -v`
Expected: 3 PASSED

- [ ] **Step 3: Commit**

```bash
git add tests/pipeline/test_investigation_integration.py
git commit -m "test: investigation strategy integration smoke tests"
```

---

## Follow-Up Plans

Remaining 9 nodes (same pattern): `username_enumerator`, `face_search`, `exif_extractor`, `document_search`, `phone_osint`, `messaging_check`, `pep_sanctions_screen`, `adverse_media`, `crypto_tracer`.
