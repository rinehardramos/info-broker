"""Security helpers for handling untrusted data.

All data flowing in from third parties (Apify/LinkedIn raw fields,
DuckDuckGo results, scraped pages, LLM output, user input) is treated
as untrusted and must pass through these helpers before reaching the
LLM, the network, or an exported spreadsheet. See tasks/todo.md Phase 6
for the threat model.
"""

from __future__ import annotations

import ipaddress
import re
import socket
from urllib.parse import urlparse

import requests

ALLOWED_URL_SCHEMES = ("http", "https")
DEFAULT_FETCH_TIMEOUT = 5
DEFAULT_FETCH_MAX_BYTES = 512 * 1024  # 512 KiB cap on response body
DEFAULT_PROMPT_SANITIZE_MAX = 4000
DEFAULT_DB_TEXT_MAX = 8000
DEFAULT_SEARCH_QUERY_MAX = 256
DEFAULT_EMBEDDING_INPUT_MAX = 4000

# Cells starting with any of these characters are interpreted as formulas
# by Excel / LibreOffice / Google Sheets and can execute on open.
_FORMULA_INJECTION_PREFIXES = ("=", "+", "-", "@", "\t", "\r")

# Postgres identifier allow-list (table / column names) — letters, digits,
# underscore, must not start with a digit, max 63 chars (pg NAMEDATALEN-1).
_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,62}$")


class UnsafeURLError(ValueError):
    """Raised when a URL fails the SSRF allow-list checks."""


def _host_is_public(host: str) -> bool:
    """Resolve `host` and confirm every address is a public unicast IP."""
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return False
    if not infos:
        return False
    for info in infos:
        addr = info[4][0]
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            return False
        # Block loopback, link-local (incl. 169.254.169.254 cloud metadata),
        # private RFC1918, multicast, reserved, and unspecified ranges.
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        ):
            return False
    return True


def safe_fetch_url(
    url: str,
    *,
    timeout: int = DEFAULT_FETCH_TIMEOUT,
    max_bytes: int = DEFAULT_FETCH_MAX_BYTES,
    headers: dict | None = None,
    allowed_content_types: tuple[str, ...] | None = None,
) -> requests.Response:
    """Fetch `url` after validating it cannot be used for SSRF.

    Enforces:
      - http/https only
      - hostname must resolve exclusively to public unicast addresses
      - response body capped at `max_bytes`
      - redirects disabled (caller must re-validate any redirect target)
    """
    parsed = urlparse(url)
    if parsed.scheme not in ALLOWED_URL_SCHEMES:
        raise UnsafeURLError(f"Scheme not allowed: {parsed.scheme!r}")
    host = parsed.hostname
    if not host:
        raise UnsafeURLError("URL is missing a hostname")
    if not _host_is_public(host):
        raise UnsafeURLError(f"Host {host!r} resolves to a non-public address")

    response = requests.get(
        url,
        headers=headers or {},
        timeout=timeout,
        allow_redirects=False,
        stream=True,
    )
    response.raise_for_status()

    if allowed_content_types is not None:
        ctype = (response.headers.get("Content-Type") or "").split(";", 1)[0].strip().lower()
        if ctype not in allowed_content_types:
            response.close()
            raise UnsafeURLError(
                f"Content-Type {ctype!r} not in allow-list {allowed_content_types}"
            )

    # Cap body size before letting the caller read .text / .content.
    chunks: list[bytes] = []
    total = 0
    for chunk in response.iter_content(chunk_size=8192):
        if not chunk:
            continue
        total += len(chunk)
        if total > max_bytes:
            response.close()
            raise UnsafeURLError(
                f"Response from {host} exceeds {max_bytes}-byte cap"
            )
        chunks.append(chunk)
    response._content = b"".join(chunks)  # populate .text / .content
    return response


def sanitize_for_prompt(
    text: str | None,
    *,
    max_length: int = DEFAULT_PROMPT_SANITIZE_MAX,
    label: str = "untrusted",
) -> str:
    """Make `text` safe(r) to embed in an LLM prompt.

    - Coerces None / non-strings to ''.
    - Strips ASCII control characters except newline and tab.
    - Truncates to `max_length` characters.
    - Wraps the result in clearly-labelled fences so the model can be
      instructed to treat the contents as data rather than instructions.
    """
    if text is None:
        text = ""
    if not isinstance(text, str):
        text = str(text)
    cleaned = "".join(
        ch for ch in text if ch in ("\n", "\t") or 0x20 <= ord(ch) < 0x7F or ord(ch) >= 0xA0
    )
    if len(cleaned) > max_length:
        cleaned = cleaned[:max_length] + "...[truncated]"
    return f"<<<BEGIN_{label.upper()}>>>\n{cleaned}\n<<<END_{label.upper()}>>>"


def escape_spreadsheet_cell(value):
    """Neutralize CSV/XLSX formula injection.

    Returns `value` unchanged unless it is a string that begins with a
    spreadsheet formula trigger, in which case a single leading
    apostrophe is prepended (the standard OWASP mitigation).
    """
    if not isinstance(value, str):
        return value
    if value and value[0] in _FORMULA_INJECTION_PREFIXES:
        return "'" + value
    return value


def escape_dataframe_cells(df):
    """Apply `escape_spreadsheet_cell` to every object/string column in `df`."""
    for col in df.select_dtypes(include=["object", "string"]).columns:
        df[col] = df[col].map(escape_spreadsheet_cell)
    return df


def coerce_db_text(value, *, max_length: int = DEFAULT_DB_TEXT_MAX) -> str:
    """Coerce an arbitrary value to a Postgres-safe text string.

    - None / non-strings are stringified.
    - NUL bytes (`\\x00`) are removed — PostgreSQL TEXT and JSONB both
      reject them and will raise mid-transaction otherwise.
    - Length is capped at `max_length` to prevent ingest-side DoS where
      a hostile upstream payload bloats a single field to megabytes.
    """
    if value is None:
        return ""
    if not isinstance(value, str):
        value = str(value)
    if "\x00" in value:
        value = value.replace("\x00", "")
    if len(value) > max_length:
        value = value[:max_length]
    return value


def scrub_jsonb(obj, *, max_string_length: int = DEFAULT_DB_TEXT_MAX):
    """Recursively strip NUL bytes and cap string lengths in a JSON-able value.

    Use before `json.dumps(...)` for any payload destined for a JSONB column.
    """
    if isinstance(obj, str):
        return coerce_db_text(obj, max_length=max_string_length)
    if isinstance(obj, dict):
        return {
            coerce_db_text(str(k), max_length=128): scrub_jsonb(v, max_string_length=max_string_length)
            for k, v in obj.items()
        }
    if isinstance(obj, (list, tuple)):
        return [scrub_jsonb(v, max_string_length=max_string_length) for v in obj]
    return obj


def validate_search_query(query, *, max_length: int = DEFAULT_SEARCH_QUERY_MAX) -> str:
    """Sanitize an LLM- or user-supplied web search query.

    Strips control characters, collapses whitespace, caps length. Returns
    empty string for unusable input so the caller can short-circuit.
    """
    if not isinstance(query, str):
        return ""
    cleaned = "".join(ch for ch in query if ch == " " or ch.isprintable())
    cleaned = " ".join(cleaned.split())
    if len(cleaned) > max_length:
        cleaned = cleaned[:max_length]
    return cleaned


def is_safe_sql_identifier(name: str) -> bool:
    """Allow-list check for any dynamically-built SQL identifier.

    All current queries are parameterized, but if future code needs to
    interpolate a table or column name (e.g. dynamic ALTER), it MUST
    pass through this check first to prevent identifier injection.
    """
    return isinstance(name, str) and bool(_IDENTIFIER_RE.match(name))


# Content-type allow-lists for safe_fetch_url callers.
HTML_CONTENT_TYPES = ("text/html", "application/xhtml+xml")
JSON_CONTENT_TYPES = ("application/json", "text/json")
