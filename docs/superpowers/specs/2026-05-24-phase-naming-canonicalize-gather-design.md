# Design: Canonicalize the broadening phase as `gather` (retire `BROADEN`)

> Date: 2026-05-24
> Status: approved (brainstorm) → pending spec review
> Related: #89 (brain BROADEN), #117 (unified taxonomy), `docs/TICKET-TRACKING.md`

## Problem

The pipeline has one phase that, depending on layer, is called two different things:

- **Structural layer** (catalog, strategist, engine, gates, telemetry, tests): `gather` — the
  domain-agnostic "collect evidence" phase in the unified taxonomy
  `extract → gather → disconfirm → synthesize` (`LEGAL_PHASE_IDS`, shipped in #117).
- **Brain-prompt layer** (`is_prompt.py`, `agent.py`, `session_service.py`): `BROADEN` — the
  ACH-heritage behavioral instruction ("≥3 live searches before ranking; one search per
  hypothesis"), which is exactly the anti-tunneling behavior #89 cares about.

This split is a coherence problem: the orchestrator/logs say `gather`; the brain is told
`BROADEN`. A reader (human or machine) cannot tell they are the same phase.

## Decision

**One vocabulary everywhere: `gather`.** `BROADEN` is retired as a label.

`gather` wins because it is already the structural id across all domains, it generalizes
(real_estate/company/lead "gather" all read naturally, "broaden a listings fetch" does not),
and `broaden` is a *legacy* phase id the `test_no_legacy_phase_ids` CI lint already forbids.
Renaming to `broaden` would revert #117 and fight the lint.

**Intent is preserved, only the label changes.** The broadening *behavior* (≥3 distinct
hypotheses, ≥1 live search each, hypothesis-first, no ranking until satisfied) remains stated
explicitly — now as requirements *of the gather phase* rather than under a separate noun.
This must read at least as forcefully as the current `BROADEN` framing (verified against #89).

Beta context: pre-#117 run data is **not** worth preserving, so backward-compat handling of
historical `"broaden"` phase rows is **removed** (simpler code) rather than kept.

## Scope — four buckets

### Bucket A — rename forward-looking prompt vocabulary → `gather`
`is_prompt.py` (~15 refs: lines 90, 95, 124, 130, 153, 169, 175, 189, 195, 197, 211, 227,
303, 483, 595), `routers/v3/agent.py:601`, `services/session_service.py:136,162,167`.
Replace `BROADEN` with "the gather phase" / "gather" while keeping every behavioral rule.
The step heading `STEP 2 — BOOTSTRAP / BROADEN` becomes `STEP 2 — BOOTSTRAP / GATHER`.

### Bucket B — update stale docstrings/comments describing current flow → `gather`
`person.py:10`, `media_identification.py:14`, `strategies/media_identification.py:9,134`,
`strategies/place.py:9`, `test_ach_strategies.py:3,32`, `test_strategist.py:1395`.
Where a docstring describes the *current* pipeline, say `gather`. Historical migration notes
that explain "was X, now Y" may keep the old word in the "was" clause for context.

### Bucket C — simplify backward-compat dual-checks → `gather` only
`ach.py:142,152`, `engine_v2.py:423`, `strategist.py:1223`: change
`phase_id in ("gather", "broaden")` → `phase_id == "gather"` and drop the now-unneeded
`# allowlist 2026-05-23` comments. Accept that pre-#117 run rows lose special phase handling.

### Bucket D — KEEP (the guardrail; it must name the forbidden word)
`test_no_legacy_phase_ids.py` `_LEGACY_IDS = [..., "broaden", ...]`, plus the helpful
legacy-id hints in `constants.py:9`, `schemas.py:97`, `audit.py:51`, and the
`test_startup_audit.py` fixtures that assert the audit *rejects* `"broaden"`. These exist to
*prevent* `broaden` from returning; they legitimately contain the word and stay (allowlisted).

### Leave as-is — genuine English, not the phase
`adverse_media.py:29` ("broaden query coverage"), `patent_prior_art.py:85` ("broadens
search"), `strategist.py:187` ("Try broadening location or budget" — a user-facing
real-estate hint). Unrelated to the phase; the lint only matches quoted `"broaden"`.
Test variable `broaden_checks` (`test_strategy_gate_audit.py:142,156`) → `gather_checks`
for token-consistency.

## Verification

1. **Lint**: `test_no_legacy_phase_ids` still passes (Bucket D intact; Buckets A–C no longer
   emit quoted `"broaden"`).
2. **Grep gate**: after the change, the only `broaden` tokens remaining in `app/` are Bucket D
   (allowlisted) and the three English-verb uses; no `BROADEN` remains as a phase label.
3. **Prompt-intent check**: re-read the rewritten `is_prompt.py` gather section and confirm the
   ≥3-hypotheses / ≥1-live-source rules are stated at least as forcefully as before.
4. **Backend tests**: `test_strategist.py`, `test_ach_strategies.py`, `test_startup_audit.py`,
   `test_no_legacy_phase_ids.py`, `test_catalogs.py` pass on the host venv.
5. **Live smoke**: one identification run still reaches gather with ≥3 hypotheses (dovetails
   with the #89 verification — if #89 is exercised in the same window, reuse its run).

## Out of scope
- The #89 behavioral fix itself (tactician slot-0, ACH floor) — separate, decided by the #89
  reproduction. This spec only changes *naming/vocabulary* + the prompt-intent wording.
- Frontend phase-label strings (none reference `broaden` per the lint's frontend scan).

## Risk
Low. No structural phase id changes (it was already `gather`). Main risk is *weakening the
prompt's anti-tunneling force* during the BROADEN→gather rewrite — mitigated by verification
step 3 and by keeping all behavioral rules verbatim, changing only the label.
