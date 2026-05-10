# Multi-Branch Retrieval for Media Identification — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:[REDACTED:high-entropy-base64:27ch:hash=88f76bb3] (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix media identification so Spider-Noir (male lead) is blocked and female-led candidates reach the confirmation card via 3 parallel TMDB retrieval branches, a TMDB lead-gender hard filter, and match-weighted confidence scoring.

**Architecture:** Before launching Claude Code brain, orchestrator runs 3 parallel TMDB branches and injects balanced corpus into prompt. After brain returns, TMDB gender check and match-weighted confidence run before confirmation card.

**Tech Stack:** Python 3.11, httpx, TMDB API v3. Copy URL and key resolution from `app/pipeline/nodes/tmdb_search.py`.

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `app/pipeline/retrieval/__init__.py` | CREATE | Package marker |
| `app/pipeline/retrieval/tmdb_client.py` | CREATE | TMDB HTTP: search_tv, get_top_cast, get_person_tv_credits, search_franchise_cast |
| `app/pipeline/retrieval/multi_branch.py` | CREATE | BranchHit, BranchEvidence, prefetch_branches() |
| `app/pipeline/retrieval/branches/__init__.py` | CREATE | Package marker |
| `app/pipeline/retrieval/branches/media_identification.py` | CREATE | 3 branch coroutines |
| `app/pipeline/fusion/constraint_filter.py` | CREATE | passes_lead_constraint() |
| `app/pipeline/fusion/scorecard.py` | MODIFY | Add query_explanatory_score() |
| `app/routers/v3/agent.py` | MODIFY | Prefetch + constraint filter |
| `app/is_brain.py` | MODIFY | Accept prefetched_evidence param |
| `app/is_prompt.py` | MODIFY | Add {prefetched_evidence} slot |
| `app/pipeline/strategies/media_identification.py` | MODIFY | One-sentence note |

---

### Task 1: TMDB client module

**Files:**
- Create: `app/pipeline/retrieval/__init__.py`
- Create: `app/pipeline/retrieval/tmdb_client.py`

- [ ] **Step 1: Create package directories**

```bash
mkdir -p app/pipeline/retrieval/branches
mkdir -p tests/pipeline/retrieval
mkdir -p tests/pipeline/fusion
touch app/pipeline/retrieval/__init__.py
touch app/pipeline/retrieval/branches/__init__.py
touch tests/pipeline/retrieval/__init__.py
touch tests/pipeline/fusion/__init__.py
```

- [ ] **Step 2: Write failing test**

Create `tests/pipeline/retrieval/test_tmdb_client.py`:

```python
import pytest
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
async def test_search_tv_returns_titles():
    from app.pipeline.retrieval.tmdb_client import search_tv
    mock_data = {"results": [{"id": 85552, "name": "Euphoria",
                               "first_air_date": "2025-01-01", "overview": "A teen drama"}]}
    with patch("app.pipeline.retrieval.tmdb_client._get",
               new_callable=AsyncMock, return_value=mock_data):
        results = await search_tv("euphoria", year_gte=2024)
    assert len(results) == 1
    assert results[0].tmdb_id == 85552
    assert results[0].type == "tv"


@pytest.mark.asyncio
async def test_get_top_cast_sorted_by_order():
    from app.pipeline.retrieval.tmdb_client import get_top_cast
    mock_data = {"cast": [
        {"id": 1, "name": "Zendaya", "gender": 1, "order": 0},
        {"id": 2, "name": "Eric Dane", "gender": 2, "order": 1},
    ]}
    with patch("app.pipeline.retrieval.tmdb_client._get",
               new_callable=AsyncMock, return_value=mock_data):
        cast = await get_top_cast(85552, media_type="tv")
    assert cast[0]["name"] == "Zendaya"
    assert cast[0]["gender"] == 1


@pytest.mark.asyncio
async def test_no_api_key_returns_empty():
    from app.pipeline.retrieval.tmdb_client import search_tv
    with patch("app.pipeline.retrieval.tmdb_client._resolve_key", return_value=None):
        results = await search_tv("anything", year_gte=2024)
    assert results == []
```

- [ ] **Step 3: Run test to verify it fails**

```bash
docker exec info-broker-info-broker-api-1 \
  python -m pytest tests/pipeline/retrieval/test_tmdb_client.py -v 2>&1 | tail -10
```

Expected: `ModuleNotFoundError`

- [ ] **Step 4: Create `app/pipeline/retrieval/tmdb_client.py`**

Open `app/pipeline/nodes/tmdb_search.py` and copy:
- `_TMDB_SEARCH_URL` constant → derive `_TMDB_BASE` by stripping `/search/{search_type}` from it
- `_resolve_api_key` function → rename to `_resolve_key`

Then implement the following interface:

```python
from __future__ import annotations
import asyncio, logging, os
from dataclasses import dataclass, field
from typing import Literal
import httpx

log = logging.getLogger(__name__)
# _TMDB_BASE: derive from tmdb_search.py _TMDB_SEARCH_URL
# _resolve_key(): copy from tmdb_search.py _resolve_api_key()

def _parse_year(date_str: str | None) -> int | None:
    if date_str and len(date_str) >= 4:
        try: return int(date_str[:4])
        except ValueError: pass
    return None

@dataclass
class TMDBTitle:
    tmdb_id: int
    title: str
    year: int | None
    type: Literal["tv", "movie"]
    overview: str
    top_cast: list[str] = field(default_factory=list)
    top_cast_genders: list[int] = field(default_factory=list)

async def _get(path: str, params: dict | None = None) -> dict:
    # Use _TMDB_BASE + path; add {"language": "en-US"} and key from _resolve_key()
    # httpx.AsyncClient timeout=8.0, raise_for_status()
    ...

async def search_tv(query: str, year_gte: int = 2024) -> list[TMDBTitle]:
    # GET /search/tv?query=..., filter year >= year_gte, return list[TMDBTitle][:10]
    ...

async def get_top_cast(tmdb_id: int, media_type: str = "tv") -> list[dict]:
    # GET /{media_type}/{tmdb_id}/credits, return cast sorted by "order"[:5]
    ...

async def get_person_tv_credits(person_id: int, year_gte: int = 2024) -> list[TMDBTitle]:
    # GET /person/{person_id}/tv_credits, filter year >= year_gte, return[:5]
    ...

async def search_franchise_cast(franchise_titles: list[str]) -> list[dict]:
    # For each title: /search/movie -> first result id -> /movie/{id}/credits
    # Collect gender==1 cast across all, dedupe by id, sort by popularity desc, return[:10]
    ...
```

- [ ] **Step 5: Run tests**

```bash
docker exec info-broker-info-broker-api-1 \
  python -m pytest tests/pipeline/retrieval/test_tmdb_client.py -v 2>&1 | tail -15
```

Expected: 3 PASSED

- [ ] **Step 6: Commit**

```bash
git add app/pipeline/retrieval/ tests/pipeline/retrieval/ tests/pipeline/fusion/
git commit -m "feat(retrieval): TMDB client — search, credits, franchise cast"
```

---

### Task 2: BranchHit / BranchEvidence / prefetch_branches

**Files:**
- Create: `app/pipeline/retrieval/multi_branch.py`

- [ ] **Step 1: Write failing test**

Create `tests/pipeline/retrieval/test_multi_branch.py`:

```python
import pytest
from unittest.mock import AsyncMock, patch
from app.pipeline.retrieval.multi_branch import (
    BranchHit, BranchEvidence, prefetch_branches, BRANCH_QUOTA,
)


def _hit(title: str, branch: str) -> BranchHit:
    return BranchHit(title=title, year=2025, type="tv", tmdb_id=None,
                     top_billed_cast=["Zendaya"], top_billed_genders=[1],
                     overview="test", source="tmdb", branch=branch)


@pytest.mark.asyncio
async def test_returns_all_three_branches():
    with patch("app.pipeline.retrieval.branches.media_identification.branch_character_in_universe",
               new_callable=AsyncMock, return_value=[_hit("Silk", "character_in_universe")]), \
         patch("app.pipeline.retrieval.branches.media_identification.branch_actor_career",
               new_callable=AsyncMock, return_value=[_hit("Euphoria S3", "actor_career")]), \
         patch("app.pipeline.retrieval.branches.media_identification.branch_genre_signal",
               new_callable=AsyncMock, return_value=[_hit("Fallout", "genre_signal")]):
        result = await prefetch_branches(
            {"primary": "girl", "supporting": "shotgun", "context": "spiderman"},
            "media_identification")
    assert set(result.branches.keys()) == {"character_in_universe", "actor_career", "genre_signal"}
    assert result.balanced is True


@pytest.mark.asyncio
async def test_caps_at_quota():
    many = [_hit(f"T{i}", "character_in_universe") for i in range(20)]
    with patch("app.pipeline.retrieval.branches.media_identification.branch_character_in_universe",
               new_callable=AsyncMock, return_value=many), \
         patch("app.pipeline.retrieval.branches.media_identification.branch_actor_career",
               new_callable=AsyncMock, return_value=[]), \
         patch("app.pipeline.retrieval.branches.media_identification.branch_genre_signal",
               new_callable=AsyncMock, return_value=[]):
        result = await prefetch_branches(
            {"primary": "girl", "supporting": "", "context": "spiderman"},
            "media_identification")
    assert len(result.branches["character_in_universe"]) == BRANCH_QUOTA
    assert result.balanced is False


@pytest.mark.asyncio
async def test_non_media_returns_empty():
    result = await prefetch_branches({"primary": "company"}, "person")
    assert result.branches == {}
    assert result.balanced is True


def test_to_prompt_block_has_all_branches():
    evidence = BranchEvidence(branches={
        "character_in_universe": [_hit("Silk", "character_in_universe")],
        "actor_career": [_hit("Euphoria S3", "actor_career")],
        "genre_signal": [_hit("Fallout", "genre_signal")],
    }, balanced=True)
    block = evidence.to_prompt_block()
    assert "Branch A" in block and "Branch B" in block and "Branch C" in block
    assert "Silk" in block and "Euphoria S3" in block
    assert "YOU MUST produce" in block
```

- [ ] **Step 2: Run to verify it fails**

```bash
docker exec info-broker-info-broker-api-1 \
  python -m pytest tests/pipeline/retrieval/test_multi_branch.py -v 2>&1 | tail -10
```

Expected: `ImportError`

- [ ] **Step 3: Create `app/pipeline/retrieval/multi_branch.py`**

```python
from __future__ import annotations
import asyncio, logging
from dataclasses import dataclass, field
from typing import Literal

log = logging.getLogger(__name__)
BRANCH_QUOTA = 5

_BRANCH_LABELS = {
    "character_in_universe": "Branch A - Character-in-Spider-Man-Universe",
    "actor_career":          "Branch B - Actress-from-Spider-Man-in-New-Series",
    "genre_signal":          "Branch C - Young-Female-Lead-Franchise-Blind",
}


@dataclass
class BranchHit:
    title: str
    year: int | None
    type: Literal["tv", "movie", "other"]
    tmdb_id: int | None
    top_billed_cast: list[str]
    top_billed_genders: list[int]
    overview: str
    source: Literal["tmdb", "web", "news"]
    branch: str
    actor_connection: str | None = None


@dataclass
class BranchEvidence:
    branches: dict[str, list[BranchHit]]
    balanced: bool

    def to_prompt_block(self) -> str:
        if not self.branches:
            return ""
        lines = ["## PRE-RETRIEVED EVIDENCE (do not re-search - work from this corpus)\n"]
        for key, label in _BRANCH_LABELS.items():
            hits = self.branches.get(key, [])
            lines.append(f"### {label}")
            if not hits:
                lines.append("*(no results)*")
            else:
                for i, h in enumerate(hits, 1):
                    cast_str = ", ".join(h.top_billed_cast[:3]) if h.top_billed_cast else "unknown"
                    conn = f" [{h.actor_connection}]" if h.actor_connection else ""
                    lines.append(
                        f"{i}. **{h.title}** ({h.year or '?'}) "
                        f"- top cast: {cast_str}{conn}\n   {h.overview[:120]}"
                    )
            lines.append("")
        lines.append(
            "**YOU MUST produce >= 1 candidate from each non-empty branch before ranking.**\n"
            'State "no viable candidate" for any branch you cannot satisfy.'
        )
        return "\n".join(lines)


async def prefetch_branches(signals: dict, classification: str) -> BranchEvidence:
    if classification != "media_identification":
        return BranchEvidence(branches={}, balanced=True)
    if not signals.get("primary") and not signals.get("context"):
        return BranchEvidence(branches={}, balanced=True)
    from app.pipeline.retrieval.branches.media_identification import (
        branch_character_in_universe, branch_actor_career, branch_genre_signal,
    )
    raw = await asyncio.gather(
        branch_character_in_universe(signals),
        branch_actor_career(signals),
        branch_genre_signal(signals),
        return_exceptions=True,
    )
    keys = ["character_in_universe", "actor_career", "genre_signal"]
    branches: dict[str, list[BranchHit]] = {}
    for key, result in zip(keys, raw):
        if isinstance(result, Exception):
            log.warning("Branch %s failed (non-fatal): %s", key, result)
            branches[key] = []
        else:
            branches[key] = list(result)[:BRANCH_QUOTA]
    return BranchEvidence(
        branches=branches,
        balanced=all(len(v) >= 1 for v in branches.values()),
    )
```

- [ ] **Step 4: Run tests**

```bash
docker exec info-broker-info-broker-api-1 \
  python -m pytest tests/pipeline/retrieval/test_multi_branch.py -v 2>&1 | tail -15
```

Expected: 4 PASSED

- [ ] **Step 5: Commit**

```bash
git add app/pipeline/retrieval/multi_branch.py tests/pipeline/retrieval/test_multi_branch.py
git commit -m "feat(retrieval): BranchHit/BranchEvidence + prefetch_branches orchestrator"
```

---

### Task 3: Three branch coroutines

**Files:**
- Create: `app/pipeline/retrieval/branches/media_identification.py`

- [ ] **Step 1: Write failing test**

Create `tests/pipeline/retrieval/test_branches_media.py`:

```python
import pytest
from unittest.mock import AsyncMock, patch
from app.pipeline.retrieval.tmdb_client import TMDBTitle


def _t(tmdb_id=1, title="Test", year=2025, genders=None):
    t = TMDBTitle(tmdb_id=tmdb_id, title=title, year=year, type="tv", overview="overview")
    t.top_cast = ["Actor"]
    t.top_cast_genders = genders or [1]
    return t


@pytest.mark.asyncio
async def test_branch_a_tagged():
    from app.pipeline.retrieval.branches.media_identification import branch_character_in_universe
    with patch("app.pipeline.retrieval.branches.media_identification.search_tv",
               new_callable=AsyncMock, return_value=[_t(1, "Silk", 2025, [1])]), \
         patch("app.pipeline.retrieval.branches.media_identification.get_top_cast",
               new_callable=AsyncMock,
               return_value=[{"name": "Cindy Moon", "gender": 1, "order": 0}]):
        result = await branch_character_in_universe(
            {"primary": "girl", "supporting": "shotgun", "context": "spiderman"})
    assert all(h.branch == "character_in_universe" for h in result)


@pytest.mark.asyncio
async def test_branch_b_actor_connection():
    from app.pipeline.retrieval.branches.media_identification import branch_actor_career
    zendaya = {"id": 505710, "name": "Zendaya", "gender": 1, "popularity": 95}
    with patch("app.pipeline.retrieval.branches.media_identification.search_franchise_cast",
               new_callable=AsyncMock, return_value=[zendaya]), \
         patch("app.pipeline.retrieval.branches.media_identification.get_person_tv_credits",
               new_callable=AsyncMock,
               return_value=[_t(85552, "Euphoria", 2025, [1])]), \
         patch("app.pipeline.retrieval.branches.media_identification.get_top_cast",
               new_callable=AsyncMock,
               return_value=[{"name": "Zendaya", "gender": 1, "order": 0}]):
        result = await branch_actor_career(
            {"primary": "girl", "supporting": "shotgun", "context": "spiderman"})
    assert len(result) >= 1
    assert "Zendaya" in result[0].actor_connection


@pytest.mark.asyncio
async def test_branch_c_tagged():
    from app.pipeline.retrieval.branches.media_identification import branch_genre_signal
    with patch("app.pipeline.retrieval.branches.media_identification.search_tv",
               new_callable=AsyncMock, return_value=[_t(209876, "Fallout", 2024, [1])]), \
         patch("app.pipeline.retrieval.branches.media_identification.get_top_cast",
               new_callable=AsyncMock,
               return_value=[{"name": "Ella Purnell", "gender": 1, "order": 0}]):
        result = await branch_genre_signal(
            {"primary": "girl", "supporting": "man has a shotgun", "context": "spiderman"})
    assert all(h.branch == "genre_signal" for h in result)
```

- [ ] **Step 2: Run to verify it fails**

```bash
docker exec info-broker-info-broker-api-1 \
  python -m pytest tests/pipeline/retrieval/test_branches_media.py -v 2>&1 | tail -10
```

Expected: `ImportError`

- [ ] **Step 3: Create `app/pipeline/retrieval/branches/media_identification.py`**

```python
from __future__ import annotations
import asyncio, logging
from app.pipeline.retrieval.multi_branch import BranchHit, BRANCH_QUOTA
from app.pipeline.retrieval.tmdb_client import (
    TMDBTitle, search_tv, get_top_cast, get_person_tv_credits, search_franchise_cast,
)

log = logging.getLogger(__name__)
_YEAR_GTE = 2024
_SPIDER_MAN_FRANCHISE = [
    "Spider-Man: No Way Home",
    "Spider-Man: Across the Spider-Verse",
    "Spider-Man: Beyond the Spider-Verse",
    "Madame Web",
    "Kraven the Hunter",
]


def _to_hit(title: TMDBTitle, branch: str, cast: list[dict] | None = None,
            actor_connection: str | None = None) -> BranchHit:
    names   = [c.get("name", "") for c in (cast or [])][:3]
    genders = [c.get("gender", 0) for c in (cast or [])][:3]
    return BranchHit(
        title=title.title, year=title.year, type=title.type,
        tmdb_id=title.tmdb_id, top_billed_cast=names, top_billed_genders=genders,
        overview=title.overview, source="tmdb", branch=branch,
        actor_connection=actor_connection,
    )


async def branch_character_in_universe(signals: dict) -> list[BranchHit]:
    """Branch A: female character IS in Spider-Man universe."""
    context = signals.get("context", "spiderman")
    queries = [
        f"{context} female lead series",
        f"new {context} series girl protagonist",
        "spider woman silk series 2025",
    ]
    results_lists = await asyncio.gather(
        *[search_tv(q, year_gte=_YEAR_GTE) for q in queries], return_exceptions=True)
    hits: list[BranchHit] = []
    seen: set[int] = set()
    for results in results_lists:
        if isinstance(results, Exception):
            continue
        for title in results:
            if title.tmdb_id and title.tmdb_id not in seen:
                seen.add(title.tmdb_id)
                cast = await get_top_cast(title.tmdb_id, media_type="tv")
                hits.append(_to_hit(title, "character_in_universe", cast))
                if len(hits) >= BRANCH_QUOTA:
                    return hits
    return hits[:BRANCH_QUOTA]


async def branch_actor_career(signals: dict) -> list[BranchHit]:
    """Branch B: actress FROM Spider-Man films in a DIFFERENT new series."""
    franchise_cast = await search_franchise_cast(_SPIDER_MAN_FRANCHISE)
    if not franchise_cast:
        return []
    credits_lists = await asyncio.gather(
        *[get_person_tv_credits(p["id"], year_gte=_YEAR_GTE) for p in franchise_cast[:5]],
        return_exceptions=True,
    )
    hits: list[BranchHit] = []
    for person, credits in zip(franchise_cast[:5], credits_lists):
        if isinstance(credits, Exception):
            continue
        for credit in credits[:2]:
            if credit.tmdb_id:
                cast = await get_top_cast(credit.tmdb_id, media_type="tv")
                hits.append(_to_hit(
                    credit, "actor_career", cast,
                    actor_connection=f"{person.get('name', '')} (from Spider-Man franchise)",
                ))
        if len(hits) >= BRANCH_QUOTA:
            break
    return hits[:BRANCH_QUOTA]


async def branch_genre_signal(signals: dict) -> list[BranchHit]:
    """Branch C: female lead + gritty action, franchise-blind."""
    primary = signals.get("primary", "girl")
    queries = [
        f"new series {primary} protagonist gritty action drama 2025",
        "new series young woman lead thriller 2025",
        "2025 streaming series female lead action drama",
    ]
    results_lists = await asyncio.gather(
        *[search_tv(q, year_gte=_YEAR_GTE) for q in queries], return_exceptions=True)
    hits: list[BranchHit] = []
    seen: set[int] = set()
    for results in results_lists:
        if isinstance(results, Exception):
            continue
        for title in results:
            if title.tmdb_id and title.tmdb_id not in seen:
                seen.add(title.tmdb_id)
                cast = await get_top_cast(title.tmdb_id, media_type="tv")
                hits.append(_to_hit(title, "genre_signal", cast))
                if len(hits) >= BRANCH_QUOTA:
                    return hits
    return hits[:BRANCH_QUOTA]
```

- [ ] **Step 4: Run tests**

```bash
docker exec info-broker-info-broker-api-1 \
  python -m pytest tests/pipeline/retrieval/test_branches_media.py -v 2>&1 | tail -15
```

Expected: 3 PASSED

- [ ] **Step 5: Commit**

```bash
git add app/pipeline/retrieval/branches/media_identification.py \
        tests/pipeline/retrieval/test_branches_media.py
git commit -m "feat(retrieval): 3-branch coroutines — character, actor-career, genre-signal"
```

---

### Task 4: Lead-character constraint filter

**Files:**
- Create: `app/pipeline/fusion/constraint_filter.py`

- [ ] **Step 1: Write failing test**

Create `tests/pipeline/fusion/test_constraint_filter.py`:

```python
import pytest
from unittest.mock import AsyncMock, patch
from app.pipeline.fusion.constraint_filter import (
    passes_lead_constraint, extract_primary_signal, PrimarySignal,
)


def test_girl_is_female():
    assert extract_primary_signal("girl").gender == "female"


def test_unknown_word():
    assert extract_primary_signal("detective").gender == "unknown"


@pytest.mark.asyncio
async def test_spider_noir_blocked():
    with patch("app.pipeline.fusion.constraint_filter.get_top_cast",
               new_callable=AsyncMock,
               return_value=[{"name": "Nicolas Cage", "gender": 2, "order": 0}]):
        result = await passes_lead_constraint(
            "Spider-Noir", 12345, "tv",
            PrimarySignal(entity="girl", gender="female", role="lead"))
    assert result.passed is False
    assert "Nicolas Cage" in result.reason


@pytest.mark.asyncio
async def test_euphoria_passes():
    with patch("app.pipeline.fusion.constraint_filter.get_top_cast",
               new_callable=AsyncMock,
               return_value=[{"name": "Zendaya", "gender": 1, "order": 0}]):
        result = await passes_lead_constraint(
            "Euphoria", 85552, "tv",
            PrimarySignal(entity="girl", gender="female", role="lead"))
    assert result.passed is True


@pytest.mark.asyncio
async def test_no_tmdb_id_passes():
    result = await passes_lead_constraint(
        "Unknown", None, "tv",
        PrimarySignal(entity="girl", gender="female", role="lead"))
    assert result.passed is True
    assert "unverified" in str(result.evidence)


@pytest.mark.asyncio
async def test_unknown_gender_always_passes():
    result = await passes_lead_constraint(
        "Any", 99, "tv",
        PrimarySignal(entity="detective", gender="unknown", role="lead"))
    assert result.passed is True
```

- [ ] **Step 2: Run to verify it fails**

```bash
docker exec info-broker-info-broker-api-1 \
  python -m pytest tests/pipeline/fusion/test_constraint_filter.py -v 2>&1 | tail -10
```

Expected: `ImportError`

- [ ] **Step 3: Create `app/pipeline/fusion/constraint_filter.py`**

```python
from __future__ import annotations
import logging
from dataclasses import dataclass
from typing import Literal
from app.pipeline.retrieval.tmdb_client import get_top_cast

log = logging.getLogger(__name__)
_FEMALE = {"girl", "woman", "female", "lady", "actress", "she", "her"}
_MALE   = {"boy", "man", "male", "guy", "actor", "he", "him"}


@dataclass
class PrimarySignal:
    entity: str
    gender: Literal["female", "male", "unknown"]
    role: Literal["lead", "supporting", "unknown"]


@dataclass
class ConstraintResult:
    passed: bool
    reason: str
    evidence: dict


def extract_primary_signal(primary_text: str) -> PrimarySignal:
    lower = primary_text.lower()
    gender: Literal["female", "male", "unknown"] = "unknown"
    if any(w in lower for w in _FEMALE):
        gender = "female"
    elif any(w in lower for w in _MALE):
        gender = "male"
    return PrimarySignal(entity=primary_text, gender=gender, role="lead")


async def passes_lead_constraint(
    candidate_title: str,
    candidate_tmdb_id: int | None,
    candidate_type: str,
    primary_signal: PrimarySignal,
) -> ConstraintResult:
    """Return False if top-billed actor gender contradicts PRIMARY. TMDB: 1=female, 2=male."""
    if primary_signal.gender == "unknown":
        return ConstraintResult(passed=True, reason="no gender constraint", evidence={})
    if not candidate_tmdb_id:
        return ConstraintResult(passed=True, reason="no TMDB id",
                                evidence={"warning": "unverified"})
    try:
        cast = await get_top_cast(candidate_tmdb_id, media_type=candidate_type or "tv")
    except Exception as exc:
        log.warning("constraint_filter TMDB error for %s: %s", candidate_title, exc)
        return ConstraintResult(passed=True, reason=f"TMDB error: {exc}", evidence={})
    if not cast:
        return ConstraintResult(passed=True, reason="no cast data", evidence={})
    top = cast[0]
    top_gender = top.get("gender", 0)
    top_name   = top.get("name", "unknown")
    if primary_signal.gender == "female" and top_gender == 2:
        return ConstraintResult(
            passed=False,
            reason=f"Lead actor {top_name!r} is male (TMDB gender=2) but PRIMARY requires female lead",
            evidence={"top_actor": top_name, "tmdb_gender": top_gender},
        )
    if primary_signal.gender == "male" and top_gender == 1:
        return ConstraintResult(
            passed=False,
            reason=f"Lead actor {top_name!r} is female (TMDB gender=1) but PRIMARY requires male lead",
            evidence={"top_actor": top_name, "tmdb_gender": top_gender},
        )
    return ConstraintResult(
        passed=True,
        reason=f"Lead actor {top_name!r} matches PRIMARY gender constraint",
        evidence={"top_actor": top_name, "tmdb_gender": top_gender},
    )
```

- [ ] **Step 4: Run tests**

```bash
docker exec info-broker-info-broker-api-1 \
  python -m pytest tests/pipeline/fusion/test_constraint_filter.py -v 2>&1 | tail -15
```

Expected: 5 PASSED

- [ ] **Step 5: Commit**

```bash
git add app/pipeline/fusion/constraint_filter.py tests/pipeline/fusion/test_constraint_filter.py
git commit -m "feat(fusion): lead-character TMDB gender constraint filter"
```

---

### Task 5: Match-weighted confidence

**Files:**
- Modify: `app/pipeline/fusion/scorecard.py`

- [ ] **Step 1: Append failing tests to `tests/pipeline/fusion/test_constraint_filter.py`**

```python
def test_spider_noir_scores_low():
    from app.pipeline.fusion.scorecard import query_explanatory_score
    candidate = {"title": "Spider-Noir", "year": 2026,
                 "top_billed_genders": [2], "overview": "1930s detective shotgun",
                 "branches": ["character_in_universe"]}
    score = query_explanatory_score(
        candidate, {"primary": "girl", "supporting": "shotgun", "context": "spiderman"})
    assert score <= 0.55  # PRIMARY fails — no +0.40


def test_euphoria_scores_high():
    import datetime
    from app.pipeline.fusion.scorecard import query_explanatory_score
    candidate = {"title": "Euphoria", "year": datetime.date.today().year,
                 "top_billed_genders": [1], "overview": "teen drama violence gun scenes",
                 "branches": ["actor_career", "genre_signal"]}
    score = query_explanatory_score(
        candidate, {"primary": "girl", "supporting": "shotgun", "context": "spiderman"})
    assert score >= 0.55  # PRIMARY +0.40, recency +0.10, multi-branch +0.10
```

- [ ] **Step 2: Run to verify it fails**

```bash
docker exec info-broker-info-broker-api-1 \
  python -m pytest tests/pipeline/fusion/test_constraint_filter.py::test_spider_noir_scores_low \
  -v 2>&1 | tail -10
```

Expected: `ImportError`

- [ ] **Step 3: Append `query_explanatory_score` to end of `app/pipeline/fusion/scorecard.py`**

```python
# ---------------------------------------------------------------------------
# Match-weighted confidence: P(query | candidate), not P(candidate exists)
# ---------------------------------------------------------------------------
import datetime as _dt

_CURRENT_YEAR_QES = _dt.date.today().year
_FEMALE_QES = {"girl", "woman", "female", "lady"}
_MALE_QES   = {"boy", "man", "male", "guy"}
_WEAPON_QES = {"shotgun", "gun", "firearm", "weapon", "pistol", "rifle"}
_SPIDER_QES = {"spider", "spiderman", "spider-man", "noir", "silk", "venom", "marvel"}


def _primary_match_qes(primary_text: str, candidate: dict) -> bool:
    lower = primary_text.lower()
    genders = candidate.get("top_billed_genders") or []
    top_g = genders[0] if genders else 0
    if any(w in lower for w in _FEMALE_QES):
        return top_g == 1
    if any(w in lower for w in _MALE_QES):
        return top_g == 2
    return True


def _supporting_match_qes(supporting_text: str, candidate: dict) -> bool:
    if not supporting_text:
        return False
    lower = supporting_text.lower()
    ov = (candidate.get("overview") or "").lower()
    return any(w in lower and w in ov for w in _WEAPON_QES)


def _context_match_qes(context_text: str, candidate: dict) -> bool:
    if not context_text:
        return True
    lower = context_text.lower()
    title_ov = ((candidate.get("title") or "") + " " + (candidate.get("overview") or "")).lower()
    if any(w in lower for w in _SPIDER_QES):
        if any(w in title_ov for w in _SPIDER_QES):
            return True
    if candidate.get("actor_connection"):
        return True
    return False


def query_explanatory_score(candidate: dict, signals: dict) -> float:
    """P(query|candidate) confidence. Weights: PRIMARY 0.40, SUPPORTING 0.25,
    CONTEXT 0.15, recency 0.10, multi-branch 0.10."""
    score = 0.0
    if _primary_match_qes(signals.get("primary", ""), candidate):
        score += 0.40
    if _supporting_match_qes(signals.get("supporting", ""), candidate):
        score += 0.25
    if _context_match_qes(signals.get("context", ""), candidate):
        score += 0.15
    year = candidate.get("year")
    if year and year >= _CURRENT_YEAR_QES - 1:
        score += 0.10
    if len(candidate.get("branches") or []) >= 2:
        score += 0.10
    return round(score, 2)
```

- [ ] **Step 4: Run all fusion tests**

```bash
docker exec info-broker-info-broker-api-1 \
  python -m pytest tests/pipeline/fusion/test_constraint_filter.py -v 2>&1 | tail -15
```

Expected: 7 PASSED

- [ ] **Step 5: Commit**

```bash
git add app/pipeline/fusion/scorecard.py tests/pipeline/fusion/test_constraint_filter.py
git commit -m "feat(fusion): query_explanatory_score — match-weighted confidence"
```

---

### Task 6: Wire into agent.py

**Files:**
- Modify: `app/routers/v3/agent.py`

- [ ] **Step 1: Add `_extract_signals_from_query` helper after `_CONFIRM_PENDING` dict**

```python
def _extract_signals_from_query(query: str) -> dict:
    """Parse PRIMARY/SUPPORTING/CONTEXT labels from enriched identification query."""
    signals = {"primary": "", "supporting": "", "context": ""}
    for line in query.splitlines():
        line = line.strip()
        if line.startswith("PRIMARY (subject to identify):"):
            signals["primary"] = line.split(":", 1)[-1].strip()
        elif line.startswith("SUPPORTING (scene details):"):
            signals["supporting"] = line.split(":", 1)[-1].strip()
        elif line.startswith("CONTEXT (franchise/platform constraints):"):
            signals["context"] = line.split(":", 1)[-1].strip()
    return signals
```

- [ ] **Step 2: Add prefetch call after `entity_strategy = await compile_strategy(...)`**

```python
        prefetched_evidence = None
        if research_category == "media_identification":
            try:
                from app.pipeline.retrieval.multi_branch import prefetch_branches
                _signals = _extract_signals_from_query(query)
                prefetched_evidence = await prefetch_branches(_signals, research_category)
                log.info("IS Brain: pre-fetched branches balanced=%s branches=%s",
                         prefetched_evidence.balanced,
                         list(prefetched_evidence.branches.keys()))
            except Exception as _pf_exc:
                log.warning("prefetch_branches failed (non-fatal): %s", _pf_exc)
```

- [ ] **Step 3: Add `prefetched_evidence=prefetched_evidence` as last kwarg to `run_research(...)`**

- [ ] **Step 4: Add constraint filter before `if should_confirm:`**

```python
            if should_confirm and research_category == "media_identification":
                try:
                    from app.pipeline.fusion.constraint_filter import (
                        passes_lead_constraint, extract_primary_signal,
                    )
                    _cf_signals = _extract_signals_from_query(query)
                    _cf_primary = extract_primary_signal(_cf_signals.get("primary", ""))
                    _cf_tmdb_id: int | None = None
                    try:
                        _cf_tmdb_id = int(top_finding.get("tmdb_id") or 0) or None
                    except (ValueError, TypeError):
                        pass
                    _cf_result = await passes_lead_constraint(
                        candidate_title=candidate_name,
                        candidate_tmdb_id=_cf_tmdb_id,
                        candidate_type=result.get("entity_type", "tv"),
                        primary_signal=_cf_primary,
                    )
                    if not _cf_result.passed:
                        log.info("Constraint filter BLOCKED %r: %s",
                                 candidate_name, _cf_result.reason)
                        should_confirm = False
                except Exception as _cf_exc:
                    log.warning("constraint_filter failed (non-fatal): %s", _cf_exc)
```

- [ ] **Step 5: Deploy and verify no errors**

```bash
python3 /Users/rinehardramos/Projects/info-broker/deploy.py app/routers/v3/agent.py 2>&1
sleep 4 && docker logs info-broker-info-broker-api-1 --since=30s 2>&1 | \
  grep -v "yahoo\|INKApi" | grep -iE "error|traceback" | head -5
```

Expected: no errors

- [ ] **Step 6: Commit**

```bash
git add app/routers/v3/agent.py
git commit -m "feat(agent): prefetch_branches + constraint filter for media_identification"
```

---

### Task 7: Wire into is_brain.py + is_prompt.py

**Files:**
- Modify: `app/is_prompt.py`
- Modify: `app/is_brain.py`

- [ ] **Step 1: Add `{prefetched_evidence}` placeholder to RESEARCH_PROMPT in `app/is_prompt.py`**

Find `{session_context}` followed by `{research_plan}` and insert `{prefetched_evidence}` between them.

- [ ] **Step 2: Add directive to BROADEN section**

Find `When the query provides labeled signals (PRIMARY / SUPPORTING / CONTEXT)` in STEP 2 BROADEN and add before it:

```
**When PRE-RETRIEVED EVIDENCE is present** (injected above the workflow):
Do NOT re-search that corpus. Work from it directly.
YOU MUST produce >= 1 candidate from each non-empty branch before ranking.
State "no viable candidate" for any branch you cannot satisfy.

```

- [ ] **Step 3: Update `build_prompt` signature and format call**

Add `prefetched_evidence: str = "",` to `build_prompt()` parameter list.
Add `prefetched_evidence=_esc(prefetched_evidence),` to `RESEARCH_PROMPT.format(...)`.

- [ ] **Step 4: Update `run_research` in `app/is_brain.py`**

Add `prefetched_evidence=None` as last param.
Before `prompt = build_prompt(...)` add:

```python
    from app.pipeline.retrieval.multi_branch import BranchEvidence
    evidence_block = (
        prefetched_evidence.to_prompt_block()
        if isinstance(prefetched_evidence, BranchEvidence) else ""
    )
```

Add `prefetched_evidence=evidence_block,` to `build_prompt(...)`.

- [ ] **Step 5: Verify prompt injection**

```bash
docker exec info-broker-info-broker-api-1 python3 -c "
from app.is_prompt import build_prompt
p = build_prompt('test', prefetched_evidence='Branch A\n1. Silk')
assert 'Branch A' in p and 'YOU MUST produce' in p
print('OK len:', len(p))
" 2>&1
```

Expected: `OK len: <number>`

- [ ] **Step 6: Deploy and verify**

```bash
python3 /Users/rinehardramos/Projects/info-broker/deploy.py app/is_prompt.py app/is_brain.py 2>&1
sleep 4 && docker logs info-broker-info-broker-api-1 --since=30s 2>&1 | \
  grep -v "yahoo\|INKApi" | grep -iE "error|traceback" | head -5
```

- [ ] **Step 7: Commit**

```bash
git add app/is_prompt.py app/is_brain.py
git commit -m "feat(prompt): inject pre-retrieved branch evidence into IS brain prompt"
```

---

### Task 8: Strategy note + integration test

**Files:**
- Modify: `app/pipeline/strategies/media_identification.py`

- [ ] **Step 1: Add one-sentence note before `tools:` in the STRATEGY string**

```
NOTE: The orchestrator pre-fetches retrieval branches (PRE-RETRIEVED EVIDENCE block above workflow). Work from that corpus; do not re-search it.
```

- [ ] **Step 2: Run all new tests**

```bash
docker exec info-broker-info-broker-api-1 \
  python -m pytest tests/pipeline/retrieval/ tests/pipeline/fusion/test_constraint_filter.py \
  -v 2>&1 | tail -20
```

Expected: 11+ PASSED

- [ ] **Step 3: Full deploy**

```bash
python3 /Users/rinehardramos/Projects/info-broker/deploy.py \
  app/pipeline/strategies/media_identification.py frontend 2>&1
```

- [ ] **Step 4: Monitor branch pre-fetch on live query**

```bash
docker logs info-broker-info-broker-api-1 --follow 2>&1 | \
  grep -E "pre-fetched branches|Constraint filter BLOCKED|IS Brain:"
```

Submit in browser: `new series with girl in spiderman where man has a shotgun` -> YouTube -> An ad

Expected log line: `IS Brain: pre-fetched branches balanced=True branches=['character_in_universe', 'actor_career', 'genre_signal']`

If Spider-Noir surfaces: `Constraint filter BLOCKED 'Spider-Noir': Lead actor 'Nicolas Cage' is male (TMDB gender=2) but PRIMARY requires female lead`

- [ ] **Step 5: Final commit**

```bash
git add app/pipeline/strategies/media_identification.py
git commit -m "feat: multi-branch retrieval complete for media_identification"
```
