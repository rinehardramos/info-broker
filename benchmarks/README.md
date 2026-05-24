# Benchmark Harness — Factual-Accuracy Eval with Anti-Gaming Guards

Repeatable benchmark that measures how well the app's templates, modes,
strategies, tactics, and techniques surface **established, citable facts** —
and that **cannot be gamed** by the brain bypassing the registered research
process.

Related: GitHub issue #145.

---

## Quick Start

```bash
# Make sure the local stack is running (docker-compose up -d)
export LOCAL_STACK_URL=http://localhost:8000
export BENCH_USERNAME=admin
export BENCH_PASSWORD=admin

# Run all gold-set items
python -m benchmarks.run_benchmark

# Run specific items only
python -m benchmarks.run_benchmark --items person-jobs-001 company-kyb-001

# Write a JSON report
python -m benchmarks.run_benchmark --out-json /tmp/report.json
```

---

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `LOCAL_STACK_URL` | `http://localhost:8000` | Base URL of the running API |
| `BENCH_USERNAME` | `admin` | Login username |
| `BENCH_PASSWORD` | `admin` | Login password |
| `BENCH_TIMEOUT_S` | `300` | Max seconds to wait per run |
| `BENCH_POLL_INTERVAL_S` | `5` | Poll interval for run status |

---

## API Keys and Live Data

Gold-set items with `must_be_live: true` expected facts require live tool
calls, which in turn require configured search/enrichment API keys:

- `web_search` — requires Bing / Serper / Brave API key
- `image_search` — requires image search API key
- `opencorporates_owner` — requires OpenCorporates API key
- `hunter_email_search` — requires Hunter.io API key
- `apollo_contact` — requires Apollo.io API key
- `pipl_people` — requires Pipl API key

Without these keys, items needing live data will correctly **fail** (gaming
guard `training_only` fires). This is expected behaviour — the benchmark
surfaces key-configuration gaps (see also issues #131, key-vault work).

Items with `must_be_live: false` (historically-stable facts) may pass even
without live search keys, as long as prior_research or training_knowledge
covers the claim and the `training_only` guard does not fire.

---

## Gold-set Schema

See `benchmarks/goldset/schema.yaml` for the full annotated schema.
Each item YAML file is a list:

```yaml
- id: person-jobs-001          # unique stable id
  query: "Who is Tim Cook?"    # exact query to POST /v3/preflight
  template: person             # optional: force strategy id
  mode: investigation          # optional: force optimization mode
  domain: person               # person | company | real_estate | due_diligence
  notes: "Optional rationale"
  expected_facts:
    - claim: "Tim Cook is the CEO of Apple Inc"
      authoritative_source: "https://www.apple.com/leadership/tim-cook/"
      must_be_live: false      # true = must come from live tool, not cache/training
```

### Adding Items

1. Create or edit a YAML file under `benchmarks/goldset/` (e.g. `my_items.yaml`).
2. Each file must be a YAML list (`- id: ...`).
3. Item `id` must be unique across **all** goldset files.
4. Provide at least one `expected_fact` with a real `authoritative_source` URL.
5. Set `must_be_live: true` for claims that require fresh evidence.
6. Verify schema: `python -m pytest tests/benchmarks/ -v` (no live stack needed).

---

## Anti-Gaming Guards

A correct-looking result reached by any of these vectors scores **zero**.
The report names the tripped guard per item.

### Guard 1 — `training_only`

**What it detects:** The run produced no real tool calls, or every branch has
`source_class ∈ {training_knowledge}`. The brain answered purely from its
training weights without contacting any external tool.

**Why it matters:** Training-data recall is not evidence. The benchmark
requires live retrieval.

### Guard 2 — `unregistered_tool`

**What it detects:** A `technique_id` appears in the trail branches that is
NOT in the registered technique catalog
(`app/pipeline/catalogs/registries/techniques/`).

**Why it matters:** Shell-outs, ad-hoc tool calls, or un-cataloged techniques
bypass the registered research process and its auditability guarantees.

### Guard 3 — `skipped_phases`

**What it detects:** The resolved strategy declared phases (e.g.
`extract → gather → disconfirm → synthesize`) but not all of them appear in
the trail's `phases` list.

**Why it matters:** Required gate checks (e.g. distinct-candidate-count,
live-source-per-hypothesis) only run within their phase. Skipping a phase
skips its gate.

### Guard 4 — `rag_shortcut`

**What it detects:** An `expected_fact` with `must_be_live: true` was
satisfied, but every contributing finding has
`source_class ∈ {prior_research}` — i.e. cached prior-run results, not fresh
live evidence.

**Why it matters:** Prior-research cache may be stale. Live facts must come
from a fresh tool call.

---

## Scoring

When no guard trips, `score_item` computes:

```
coverage       = matched_facts / total_expected_facts
source_quality = mean weight of best source_class across matched facts
item_score     = coverage × source_quality
```

Source-class quality weights (higher = better provenance):

| source_class | weight |
|---|---|
| `live_official` / `primary_official` | 1.00 |
| `registry` | 0.95 |
| `live_search` | 0.75 |
| `news` | 0.65 |
| `aggregator` | 0.55 |
| `social` | 0.45 |
| `prior_research` | 0.30 |
| `training_knowledge` | 0.10 |

A fact is "matched" when:
1. ≥ 60 % of its salient tokens appear in the run's findings text, AND
2. at least one finding has a non-empty `source_url`.

---

## Output

The driver emits:

1. **Console table** — per-item id, score, coverage, source_quality, guard tripped.
2. **JSON report** — full per-item results + aggregates by strategy / mode /
   domain / technique.

Aggregate report shape:

```json
{
  "overall": { "mean_score": 0.72, "total_items": 6, "gamed_items": 1, "gamed_pct": 16.7 },
  "by_strategy": { "person": { "mean_score": 0.80, "n": 2 }, ... },
  "by_mode": { ... },
  "by_domain": { ... },
  "by_technique": { "web_search": { "mean_score": 0.75, "n": 5 }, ... }
}
```

---

## Unit Tests (no live stack required)

```bash
.venv/bin/pytest tests/benchmarks/ -v
```

Tests cover:
- Each of the 4 anti-gaming guards zeroing the score with the guard named.
- A clean run scoring proportionally to coverage and source quality.
- Partial coverage scoring proportionally.
- Source-quality weighting.
- Gold-set YAML parsing and schema validation.

---

## File Structure

```
benchmarks/
  __init__.py
  run_benchmark.py   — driver: preflight → confirm → poll → trail → score
  score.py           — pure scoring + anti-gaming logic (unit-testable)
  README.md          — this file
  goldset/
    schema.yaml      — annotated field schema
    items.yaml       — initial curated gold-set (6 items)

tests/benchmarks/
  __init__.py
  test_score.py      — unit tests for score.py (no live runs)
```
