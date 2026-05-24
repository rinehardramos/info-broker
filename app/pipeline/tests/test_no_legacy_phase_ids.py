"""CI lint: legacy phase ids must not reappear in live code.

Per spec 2026-05-23-research-skeleton-tactic-completion, the unified phase
taxonomy is extract / gather / disconfirm / synthesize. The 4 legacy ids
(signal_extraction, broaden, red_team, rank_verify) are retired.

Allowlist comments (`# allowlist 2026-05-23`) on lines that legitimately
reference legacy ids (e.g. trail-rendering for historical DB rows, test
fixtures that exist to verify rejection) are honored.
"""
from __future__ import annotations
import re
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[3]
_LEGACY_IDS = ["signal_extraction", "broaden", "red_team", "rank_verify"]  # allowlist 2026-05-23
# Match the string in source with either single or double quotes so that
# single-quoted TS literals (e.g. 'signal_extraction') are also caught.  # allowlist 2026-05-23
_PATTERN = re.compile(r'["\'](' + "|".join(_LEGACY_IDS) + r')["\']')


def _scan_dir(path: Path, suffixes: tuple[str, ...]) -> list[tuple[Path, int, str]]:
    hits: list[tuple[Path, int, str]] = []
    if not path.exists():
        return hits
    for f in path.rglob("*"):
        if not f.is_file() or f.suffix not in suffixes:
            continue
        if "__pycache__" in f.parts or "node_modules" in f.parts:
            continue
        try:
            for i, line in enumerate(f.read_text().splitlines(), start=1):
                if "# allowlist 2026-05-23" in line:
                    continue
                # TypeScript allowlist comment alternative
                if "// allowlist 2026-05-23" in line:
                    continue
                if _PATTERN.search(line):
                    hits.append((f, i, line.strip()))
        except (UnicodeDecodeError, PermissionError):
            continue
    return hits


def test_no_legacy_phase_ids_in_app():
    """No quoted legacy phase id in app/ except allowlisted lines."""
    hits = _scan_dir(_REPO_ROOT / "app", (".py",))
    assert not hits, (
        "Legacy phase ids found in app/ — rename to the unified taxonomy "
        "(extract/gather/disconfirm/synthesize) or add a `# allowlist 2026-05-23` "
        "comment on the same line if the reference is legitimate (e.g. trail-rendering "
        "for historical DB rows, or a test fixture verifying rejection).\n"
        + "\n".join(f"  {p}:{ln}: {text}" for (p, ln, text) in hits)
    )


def test_no_legacy_phase_ids_in_frontend_src():
    """No quoted legacy phase id in frontend/src/."""
    fe_dir = _REPO_ROOT / "frontend" / "src"
    if not fe_dir.exists():
        return
    hits = _scan_dir(fe_dir, (".ts", ".tsx"))
    assert not hits, (
        "Legacy phase ids found in frontend/src/ — rename or add a "
        "`// allowlist 2026-05-23` comment on the same line if legitimate.\n"
        + "\n".join(f"  {p}:{ln}: {text}" for (p, ln, text) in hits)
    )
