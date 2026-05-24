# tests/conftest.py
# Ensure real psycopg2 is imported before any test module can stub it.
#
# tests/knowledge/test_curator.py and test_llm_curator.py use
#   sys.modules.setdefault("psycopg2", stub)
# which is a no-op if psycopg2 is already present in sys.modules.
# By importing it here (conftest.py is collected/executed before test modules
# are imported), the real psycopg2 is locked in place and app.routers.v3.db
# gets the genuine driver regardless of test collection order.
import psycopg2  # noqa: F401
import psycopg2.extras  # noqa: F401

# Pin Temporal env vars before any test module triggers load_dotenv().
#
# tests/test_api.py imports `ingest` which calls load_dotenv() at module level.
# The project .env sets TEMPORAL_HOST=temporal and IS_USE_TEMPORAL=true (Docker
# hostnames). load_dotenv() only sets env vars that are NOT already present, so
# we pre-set them here (before any test is imported) to prevent .env from
# overriding to Docker-only values.
import os as _os
_os.environ.setdefault("TEMPORAL_HOST", "localhost")
_os.environ.setdefault("IS_USE_TEMPORAL", "false")
# Disable the slowapi rate limiter under test (#130): the suite makes hundreds
# of requests from one client IP, tripping the 60/min default and causing flaky
# 429s ("Rate limit exceeded: 60 per 1 minute") on login-heavy tests. Must be
# set before app import so the Limiter is constructed with enabled=False.
_os.environ.setdefault("DISABLE_RATE_LIMIT", "1")
# Bypass the run admission gate under test (#130): GLOBAL_MAX_CONCURRENT is 2,
# so any stuck/concurrent runs in the shared dev DB make `check_admission` 429
# every /v3/agent/message in the suite. Tests shouldn't depend on global run
# capacity. Read at admission_gate import time.
_os.environ.setdefault("GATE_ENABLED", "false")
