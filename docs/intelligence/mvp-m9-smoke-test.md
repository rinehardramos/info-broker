# MVP-M9 Manual Smoke Test -- Issue #89 Regression

**Purpose:** Verify the engine_v2 pipeline structurally prevents the Zhao Lusi
tunneling failure from issue #89. This test requires a live Claude Code
subprocess and real MCP tools, so it cannot be fully automated.

**Related:** `app/pipeline/tests/test_engine_v2.py::test_89_regression_simulation_with_canned_data`
(simulated regression with canned data -- proves wiring is correct given proper brain output)

---

## Environment Setup

1. Start the backend: `uvicorn app.main:app --reload`
2. Start the frontend: `cd frontend && npm run dev`
3. Ensure Claude Code is authenticated: `claude auth login` (or set `ANTHROPIC_API_KEY` in DB `core_settings`)
4. Ensure the MCP server is running and healthy
5. Provision a wallet with >= 50 RU for the test user account (use the `/v3/wallet/topup` endpoint or DB insert)

## URL

Navigate to:

```
http://localhost:5173/research?engine=v2
```

---

## Exact Query String (#89)

```
asian girl with mole in cheek bone and has an advertisement where she uses a curling iron
```

This is the exact query from run `873e093f-5af6-469c-a0d5-8f972e6473b5` that
originally tunneled to Zhao Lusi without exploring alternatives.

---

## Execution Steps

1. Open `http://localhost:5173/research?engine=v2`
2. Paste the exact query string above into the query input
3. Submit (Enter or Send button)
4. The PreflightPanel should appear with:
   - `mode: investigation`
   - `strategy: media_identification`
   - `hypothesis_count: competing` (minimum enforced by strategy floor)
   - RU estimate and wallet snapshot
5. Click **Run** (or Confirm)
6. Watch the live view panel -- you should see `is.phase_start` events for each phase:
   - `signal_extraction`
   - `broaden`
   - `disconfirm` (if reached)
   - `rank_verify` (if reached)
7. Wait for `is.run_complete` event (may take several minutes)

---

## What to Inspect After Run Completes

### In the UI

- The live view should show multiple distinct candidate cards (not just Zhao Lusi)
- At least one `is.tool_call` card should reference a non-RAG tool (web search, image search, etc.)

### In the Database

Query the `research_trails` table for the completed run:

```sql
SELECT
  run_id,
  query,
  trail->>'branches' AS branches,
  trail->>'status' AS status,
  trail->>'ranked_candidates' AS ranked_candidates
FROM research_trails
WHERE query LIKE '%curling iron%'
ORDER BY created_at DESC
LIMIT 1;
```

Inspect the `branches` JSON array. Each entry should have:

```json
{
  "phase_id": "broaden",
  "slot_idx": 0,
  "candidate_name": "<name>",
  "source_class": "<tool_name>",
  "confidence": 0.7
}
```

---

## Pass Criteria

All three conditions must hold:

1. **Distinct candidates:** `branches` contains >= 3 entries with distinct `candidate_name`
   values across the `broaden` phase. The three candidates must represent genuinely
   different identities (not three facets of Zhao Lusi).

2. **Live source requirement:** At least one finding per candidate must have
   `source_class` that is NOT in `{prior_research, training_knowledge}`.
   Acceptable source classes include: `web_search_live`, `image_search_live`,
   `news_search_live`, or any technique ID from the techniques catalog.

3. **Anti-tunneling:** The `ranked_candidates` array in the trail must contain >= 2
   candidates whose identity is distinct from Zhao Lusi. If Zhao Lusi appears in
   the list, she must be ranked alongside at least 2 other candidates with
   independent evidence chains.

---

## Fail Criteria

The test fails if any of the following are true:

- All `branches` in `broaden` phase name the same candidate (tunneling)
- All findings have `source_class` in `{prior_research, training_knowledge}` (RAG anchor)
- `ranked_candidates` contains only one identity (or all names resolve to Zhao Lusi variants)
- The run terminates early with `gate_failed` before reaching `broaden` phase

---

## Notes

- The engine_v2 classifier stub always returns `media_identification` strategy (MVP scope)
- `scoped_brain.py` spawns one Claude Code subprocess per tactician slot -- each slot
  sees only its own `unit_of_work`, not peer slots. This is the structural anti-tunneling guarantee.
- If the run terminates at the `signal_extraction` gate, increase the `hypothesis_count`
  dial to `adversarial` in the PreflightPanel before confirming.
- The automated regression in `test_engine_v2.py::test_89_regression_simulation_with_canned_data`
  proves the gate logic is correctly wired; this smoke test proves the brain actually
  diverges when given the real query.
