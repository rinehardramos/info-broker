"""Defense-in-depth lint: forbid string-built SQL queries.

Ruff S608 catches the same patterns at lint time, but a `# noqa` can
silence it. This test runs in pytest so it cannot be silenced without
a code review noticing.

Forbidden patterns inside `cur.execute(...)`, `cur.executemany(...)`,
`conn.execute(...)`, `pd.read_sql_query(...)`, etc.:

    cur.execute(f"SELECT ... {var}")          # f-string
    cur.execute("SELECT ... {}".format(var))  # .format
    cur.execute("SELECT ... %s" % var)        # % interpolation
    cur.execute("SELECT " + var)              # string concatenation

Allowed:

    cur.execute("SELECT ... WHERE id = %s", (var,))   # parameterized
    cur.execute(\"\"\"...static SQL...\"\"\")          # static literal
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent
SQL_EXECUTING_CALLS = {
    "execute",
    "executemany",
    "executescript",
    "read_sql",
    "read_sql_query",
    "read_sql_table",
}
# Files we deliberately exclude (test fixtures that intentionally build
# unsafe SQL to assert the lint catches them — none today, but reserved).
EXCLUDED_FILES: set[str] = set()


def _iter_project_py_files() -> list[Path]:
    files = []
    for p in PROJECT_ROOT.rglob("*.py"):
        if any(part in {".venv", "venv", "__pycache__", ".git"} for part in p.parts):
            continue
        if p.name in EXCLUDED_FILES:
            continue
        files.append(p)
    return sorted(files)


def _is_sql_executor(call: ast.Call) -> bool:
    """True if `call` looks like a SQL-executing call (cur.execute, etc.)."""
    func = call.func
    if isinstance(func, ast.Attribute):
        return func.attr in SQL_EXECUTING_CALLS
    if isinstance(func, ast.Name):
        return func.id in SQL_EXECUTING_CALLS
    return False


def _first_arg(call: ast.Call) -> ast.AST | None:
    return call.args[0] if call.args else None


def _is_unsafe_sql_arg(node: ast.AST) -> tuple[bool, str]:
    """Return (is_unsafe, reason) for a SQL-call's first positional arg."""
    if isinstance(node, ast.JoinedStr):  # f"..."
        return True, "f-string SQL"
    if isinstance(node, ast.BinOp):
        if isinstance(node.op, ast.Mod):  # "..." % var
            return True, "%-formatted SQL"
        if isinstance(node.op, ast.Add):  # "..." + var
            # Allow string-literal concatenation of two static strings
            # (common when splitting long static SQL across lines).
            if _is_static_string(node.left) and _is_static_string(node.right):
                return False, ""
            return True, "concatenated SQL"
    if isinstance(node, ast.Call):
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr == "format":
            return True, ".format()-built SQL"
    return False, ""


def _is_static_string(node: ast.AST) -> bool:
    """True if `node` is a string literal or a tree of string literals concatenated with +."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return True
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return _is_static_string(node.left) and _is_static_string(node.right)
    return False


def _scan_file(path: Path) -> list[tuple[int, str]]:
    """Return a list of (lineno, reason) violations in `path`."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:
        return []
    violations: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not _is_sql_executor(node):
            continue
        first = _first_arg(node)
        if first is None:
            continue
        unsafe, reason = _is_unsafe_sql_arg(first)
        if unsafe:
            violations.append((node.lineno, reason))
    return violations


@pytest.mark.parametrize("path", _iter_project_py_files(), ids=lambda p: p.name)
def test_no_string_built_sql(path: Path) -> None:
    """Every SQL-executing call must use a static string + parameters."""
    violations = _scan_file(path)
    if violations:
        rendered = "\n".join(
            f"  {path.relative_to(PROJECT_ROOT)}:{lineno} — {reason}"
            for lineno, reason in violations
        )
        pytest.fail(
            "String-built SQL detected — pass values as parameters instead "
            "of interpolating them into the query string:\n" + rendered
        )


def test_lint_actually_finds_known_bad_pattern(tmp_path: Path) -> None:
    """Self-test: the scanner must catch each forbidden pattern."""
    bad = tmp_path / "bad.py"
    bad.write_text(
        "def f(cur, x):\n"
        "    cur.execute(f'SELECT {x}')\n"
        "    cur.execute('SELECT {}'.format(x))\n"
        "    cur.execute('SELECT %s' % x)\n"
        "    cur.execute('SELECT ' + x)\n"
    )
    violations = _scan_file(bad)
    reasons = {r for _, r in violations}
    assert reasons == {
        "f-string SQL",
        ".format()-built SQL",
        "%-formatted SQL",
        "concatenated SQL",
    }


def test_lint_allows_parameterized_and_static(tmp_path: Path) -> None:
    """Self-test: parameterized + static-literal SQL must be accepted."""
    good = tmp_path / "good.py"
    good.write_text(
        "def f(cur, x):\n"
        "    cur.execute('SELECT * FROM t WHERE id = %s', (x,))\n"
        "    cur.execute('''\n"
        "        SELECT a, b\n"
        "        FROM t\n"
        "        WHERE c = %s\n"
        "    ''', (x,))\n"
        "    cur.execute('SELECT a '\n"
        "                'FROM t')\n"  # implicit string-literal concatenation
    )
    assert _scan_file(good) == []
