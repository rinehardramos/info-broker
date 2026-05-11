# IS Brain Rejection Handling Cleanup — Implementation Spec

**Date:** 2026-05-10
**Audience:** Implementer (Sonnet)
**Goal:** Remove case-specific rejection patches from the IS brain prompt and session context. Let the existing 7-step methodology (STEP 0 through STEP 7) handle E5 user rejections naturally — STEP 0 (decompose with rejection as constraint), STEP 1 (clarification gate), STEP 2 (BROADEN from retained signals), STEP 5 (adversarial check). Inject only a small generic E5 context block; do not duplicate or pre-empt methodology phases.

This is a **mechanical cleanup**. No design decisions are required. Exact line ranges, exact replacement text, and exact verification steps are below.

---

## Section 1 — What to remove

### 1.1 `app/is_prompt.py`

**Delete the entire `POST-REJECTION SELF-REFLECTION` section, including its trailing `---` separator and the blank line before `### STEP 0`.**

Exact lines to delete: **lines 53 through 80 inclusive** (28 lines).

Lines 53–80 of `/Users/rinehardramos/Projects/info-broker/app/is_prompt.py` currently contain:

```
(line 53)
(line 54) ### POST-REJECTION SELF-REFLECTION (runs BEFORE STEP 0 when [USER REJECTION — E5] is present)
(line 55)
(line 56) If the session context contains `[USER REJECTION — E5]`, execute this before anything else:
(line 57)
(line 58) **Phase 1 — Diagnose the failure:**
(line 59) Think through: Why was my prior answer plausible but wrong?
(line 60)   - Did I anchor to the wrong entity/franchise when I should have stayed broader?
(line 61)   - Did I assume single-source content when it might have been composite (ad/promo)?
(line 62)   - Was my platform assumption wrong? (e.g. I assumed Prime Video but user confirmed YouTube)
(line 63)   - Did I confirm a finding that fits the description but isn't what the user actually saw?
(line 64)   - What bias (training data, anchoring, confirmation) led me to the wrong conclusion?
(line 65)
(line 66) **Phase 2 — Identify the discriminating gap:**
(line 67) What ONE piece of information, if I had it, would eliminate at least half the remaining hypotheses?
(line 68) This is not a gap you look up — it's something only the user knows (what they directly observed).
(line 69)
(line 70) **Phase 3 — Ask, then investigate:**
(line 71) Formulate 1-2 targeted discriminating questions. Then call ask_user() with them — one at a time.
(line 72)   - Good: specific, binary or small multiple-choice, eliminates multiple hypotheses per answer
(line 73)   - Bad: vague open-ended, doesn't discriminate between candidates
(line 74)   - NEVER ask something you could find with a web search — only ask what the user uniquely knows
(line 75)
(line 76) (line 76) DO NOT start BROADEN until you have asked and received at least one clarifying answer.
(line 77) After receiving the answer, proceed to STEP 0 with the enriched context.
(line 78)
(line 79) ---
(line 80)
```

After deletion, line 52 (`## YOUR WORKFLOW`) must be immediately followed by `### STEP 0 — DECOMPOSE AND ASK IF GAPS` (currently line 81), separated by exactly one blank line.

**Result after edit:** the `## YOUR WORKFLOW` heading is followed directly by `### STEP 0`. No mention of "POST-REJECTION", "Phase 1 / Phase 2 / Phase 3", or "Self-Reflection" remains anywhere in `is_prompt.py`.

### 1.2 `app/services/session_service.py`

**Delete the entire current `rejection_section` construction block** in `build_session_context()`.

Exact lines to delete: **lines 130 through 170 inclusive** (41 lines), comprising:

- Line 130: `    # Build rejection context if this is a rejection turn`
- Line 131: `    rejection_section = ""`
- Lines 132–170: the `if is_rejection_turn(current_message):` block, including:
  - The `try:` / `from app.pipeline.fusion.grade_feedback import extract_near_probable_seeds` import
  - The `seeds = extract_near_probable_seeds(key_findings)` call
  - The `rejected_titles` list comprehension
  - The `first_rejected = rejected_titles[0] if rejected_titles else "the prior finding"` assignment
  - The hardcoded `rejection_section = f"""…"""` block containing:
    - The `[USER REJECTION — E5: …]` heading
    - The `Rejected hypothesis (DO NOT re-propose):` block
    - The `MANDATORY: SELF-REFLECTION BEFORE ANY RESEARCH` block (numbered 1–4)
    - The Spider-Man / Tom Holland / Zendaya / MJ examples
    - The H_COMPOSITE example
    - The `ANCHOR after clarification:` block referencing `seeds`
    - The `DO NOT start BROADEN until …` line
  - The `except Exception as exc:` handler with `log.warning("Rejection context build failed (non-fatal): %s", exc)`

Replace those 41 lines with the new block in **Section 2** below.

**Note:** The `extract_near_probable_seeds` import must be retained in the new block (it is still used to extract retained signals). The `first_rejected` variable must be removed entirely — it is not used anywhere else.

---

## Section 2 — Replacement text

Insert the following block in `app/services/session_service.py` at the same indentation level as the deleted code (4 spaces — inside `build_session_context`), positioned immediately after line 128 (the `findings_text = …` assignment) and immediately before the `return f"""## SESSION CONTEXT` line.

```python
    # Build rejection context if this is a rejection turn.
    # Keep this block GENERIC — no entity-specific examples, no special phases.
    # The IS brain's existing STEP 0 through STEP 7 methodology already handles
    # rejections correctly: STEP 0 re-decomposes with the rejection as a
    # constraint, STEP 1 asks discriminating questions, STEP 2 BROADENs from
    # retained signals, STEP 5 runs the adversarial check against rejected
    # evidence. Do not duplicate or pre-empt those phases here.
    rejection_section = ""
    if is_rejection_turn(current_message):
        try:
            from app.pipeline.fusion.grade_feedback import extract_near_probable_seeds
            seeds = extract_near_probable_seeds(key_findings)
            rejected_titles = [f.get("title", "?") for f in key_findings[:5]]
            rejected_block = (
                "\n".join(f"  - {t}" for t in rejected_titles)
                if rejected_titles else "  (none recorded)"
            )
            retained_block = (
                "\n".join(f"  - {s}" for s in seeds)
                if seeds else "  (none — re-derive from genesis query)"
            )
            rejection_section = f"""
[USER REJECTION — E5]
The user has confirmed the prior findings do not match their direct observation.
Apply E5 grading (primary-observer rejection) to the rejected items below and
re-run the standard methodology from STEP 0 with this rejection as a constraint.

Rejected findings (do not re-propose; treat as disconfirming evidence in ACH):
{rejected_block}

Retained signals (still valid; use as BROADEN seeds):
{retained_block}

Re-enter the methodology at STEP 0. Decompose the genesis query against the
retained signals, run STEP 1's clarification gate if a critical gap remains,
BROADEN from the retained signals (not from the rejected entity's family),
and apply the STEP 5 adversarial check against the rejected evidence before
delivering. H_COMPOSITE remains available as a hypothesis. Confidence on any
new candidate is bounded by H_COMPOSITE and ACH consistency with the rejection.
"""
        except Exception as exc:
            log.warning("Rejection context build failed (non-fatal): %s", exc)
```

**Properties of this replacement (verify each holds):**

1. **Generic** — no proper nouns, no franchise references, no platform names, no entity-type-specific language. Works identically for person, company, media, product investigations.
2. **No hardcoded examples** — no "Tom Holland", "Spider-Man", "Zendaya", "MJ", "Prime Video", "YouTube", "ad/promo".
3. **No special phases** — no "Phase 1/2/3", no "SELF-REFLECTION", no "MANDATORY" pseudo-step. Only references existing methodology by name (`STEP 0`, `STEP 1`, `STEP 5`, `BROADEN`, `H_COMPOSITE`, `ACH`).
4. **States only the four required facts:**
   - (a) E5 grade applied to rejected items
   - (b) Rejected findings listed
   - (c) Retained signals extracted (via `extract_near_probable_seeds`)
   - (d) Instruction to re-enter the methodology at STEP 0
5. **`first_rejected` is removed** — the variable is not declared anywhere in the new block.

---

## Section 3 — Verification

Run each of the following from the repository root (`/Users/rinehardramos/Projects/info-broker`). Every check must pass.

### 3.1 Confirm removed strings are gone

```bash
# Should print nothing (no matches anywhere in the prompt or session service):
grep -nE 'first_rejected|POST-REJECTION|SELF-REFLECTION|Phase 1 —|Phase 2 —|Phase 3 —' \
    app/is_prompt.py app/services/session_service.py

# Should print nothing — Spider-Man / Tom Holland / Zendaya / MJ examples are gone:
grep -niE 'spider[- ]?man|spider[- ]?noir|tom holland|zendaya|\bMJ\b|prime video' \
    app/is_prompt.py app/services/session_service.py

# Should print nothing — no "ad/promo" example, no "ad, or organic" rejection-block phrasing
# remaining inside the rejection_section (the STEP 0 menu in is_prompt.py legitimately
# mentions "ad" — that is fine; restrict the check to session_service.py):
grep -niE 'ad/promo|standalone YouTube' app/services/session_service.py
```

Each command must produce **zero lines of output**.

### 3.2 Confirm replacement block is present and well-formed

```bash
# Must match exactly once — the new generic header:
grep -c '^\[USER REJECTION — E5\]$' app/services/session_service.py
# Expected: 1

# Must reference the existing methodology by name:
grep -E 'STEP 0|STEP 1|STEP 5|BROADEN|H_COMPOSITE|ACH' app/services/session_service.py
# Expected: at least one match per token, all inside build_session_context.

# Retained-signals extraction is still wired:
grep -n 'extract_near_probable_seeds' app/services/session_service.py
# Expected: exactly one import and one call, both inside build_session_context.
```

### 3.3 Confirm `is_prompt.py` workflow is intact and uninterrupted

```bash
# `## YOUR WORKFLOW` must be immediately followed by `### STEP 0` (one blank line between):
awk '/^## YOUR WORKFLOW$/{f=1; next} f && NF{print; exit}' app/is_prompt.py
# Expected output: ### STEP 0 — DECOMPOSE AND ASK IF GAPS
```

### 3.4 Syntax / import check

```bash
python -c "from app.is_prompt import build_prompt; print(build_prompt('test query')[:200])"
python -c "from app.services.session_service import build_session_context, is_rejection_turn; \
print(build_session_context({'genesis_query':'q','conversation_thread':[],'accumulated_summary':'','key_findings':[{'title':'X','confidence':50}],'turn_count':1}, 'none of these are right'))"
```

Both commands must execute without error. The second command's output must:
- Contain `[USER REJECTION — E5]`
- Contain `Rejected findings`
- Contain `Retained signals`
- Contain a reference to `STEP 0`
- **Not** contain `Phase 1`, `Phase 2`, `Phase 3`, `SELF-REFLECTION`, `Spider-Man`, `Tom Holland`, `Zendaya`, `MJ`, or `first_rejected`.

### 3.5 Existing tests

```bash
# Run the session-service / is_prompt test modules if present:
pytest -q tests/services/test_session_service.py tests/test_is_prompt.py 2>/dev/null \
  || pytest -q -k 'session or is_prompt or rejection'
```

All collected tests must pass. If a test asserts on the deleted strings ("POST-REJECTION", "Phase 1", "Spider-Man", `first_rejected`), update the assertion to check the new generic strings (`[USER REJECTION — E5]`, `Rejected findings`, `Retained signals`, `STEP 0`) — those are the only test changes permitted by this spec.

### 3.6 Lint

```bash
ruff check app/is_prompt.py app/services/session_service.py
```

Must report no new violations introduced by this change.

---

## Out of scope

- Do **not** modify `extract_near_probable_seeds` or any other function in `app/pipeline/fusion/grade_feedback.py`.
- Do **not** modify `_REJECTION_PATTERNS`, `is_rejection_turn`, `classify_turn`, `_call_classifier`, `distil_summary`, `build_conversational_reply`, or `update_session_after_run`.
- Do **not** modify the seven STEP sections (STEP 0 – STEP 7) of `RESEARCH_PROMPT` in `is_prompt.py`. They already handle rejection naturally — that is the entire premise of this cleanup.
- Do **not** add new tests for rejection handling beyond updating existing assertions to the new strings. Behavior is covered by the existing methodology and its existing tests.
