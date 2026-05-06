"""
secrets_loader.py — Thin OpenBao secrets loader.

Copy this module into any Python project. At application startup, call:

    from secrets_loader import load_secrets
    load_secrets("my-project")

The loader authenticates via AppRole and injects secrets from:
  - secret/shared       (keys shared across all projects)
  - secret/<project>    (project-specific keys)

into os.environ using setdefault, so existing env vars are never overwritten.

If OPENBAO_ADDR / OPENBAO_ROLE_ID / OPENBAO_SECRET_ID are not set, the loader
is a no-op and the application continues using whatever env vars are already set.

Required env vars:
    OPENBAO_ADDR        e.g. http://localhost:8200
    OPENBAO_ROLE_ID     AppRole role_id (not secret)
    OPENBAO_SECRET_ID   AppRole secret_id (treat as a password)

Dependencies:
    hvac>=2.3.0
"""

import logging
import os

log = logging.getLogger(__name__)


def load_secrets(project_name: str = "default") -> None:
    """Load secrets from OpenBao into os.environ.

    Args:
        project_name: The project slug used as the KV path (e.g. "info-broker").
                      Secrets are read from secret/shared and secret/<project_name>.
    """
    addr = os.getenv("OPENBAO_ADDR")
    role_id = os.getenv("OPENBAO_ROLE_ID")
    secret_id = os.getenv("OPENBAO_SECRET_ID")

    if not all([addr, role_id, secret_id]):
        log.info("OpenBao not configured -- using env vars directly")
        return

    try:
        import hvac  # noqa: PLC0415  (lazy import keeps hvac optional at import time)

        client = hvac.Client(url=addr)
        client.auth.approle.login(role_id=role_id, secret_id=secret_id)
    except Exception as exc:
        log.error("OpenBao connection failed: %s -- falling back to env vars", exc)
        return

    for path in ["shared", project_name]:
        try:
            resp = client.secrets.kv.v2.read_secret_version(path=path)
            data: dict = resp["data"]["data"]
            for key, value in data.items():
                os.environ.setdefault(key, str(value))
            log.info("Loaded %d secrets from secret/%s", len(data), path)
        except Exception as exc:
            log.warning("Failed to read secret/%s: %s", path, exc)
