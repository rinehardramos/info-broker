"""Media identification strategy module."""

ENTITY_TYPE = "media_identification"

STRATEGY = """
=== MEDIA IDENTIFICATION STRATEGY ===

goal: Identify unknown show/movie/media clip/advertisement from partial descriptions.
execution_model: log_cycle(PIR + hypotheses) → MULTI-HYPOTHESIS(≥4 before searching) → BROADEN(≥1 search/hypothesis) → RED_TEAM(mandatory disconfirm per H) → RANK → RECURSE → DELIVER

--- PIR TEMPLATE ---

PIR: What show, film, or advertisement does the user's description refer to?
MANDATORY: Content type matches user-described medium (show vs. ad vs. film) | Subject or lead matches user's PRIMARY descriptor
SUPPORTING: Franchise or IP connection present | Release year in stated time window | Platform identified
REJECT IF: Multiple MANDATORY criteria fail and no hypothesis scores above 20%

--- STEP 1.5 — COMPETING HYPOTHESES (cold-start, before searching) ---

Generate ≥3 hypotheses from signals ONLY — no search, no training-data recall of specific titles yet.

Required hypotheses:
H1: Literal franchise interpretation (show/movie IN the named franchise/IP)
H2: Actor-Career interpretation (performer FROM the franchise in a NEW, different project — ad, show, film)
H3: Genre-blind (PRIMARY + SUPPORTING signals only; CONTEXT/franchise signal dropped entirely)
H4: Long-tail candidate (low-popularity, recent, not returned by obvious search)

Anti-anchor rule: H1 is always formulated. H2–H4 must be INDEPENDENT interpretations, not variations of H1.

Medium-type awareness: If PreFlight clarifications include "advertisement" or "YouTube", add to each hypothesis whether it could be an ad campaign, not a show.

Output format:
HYPOTHESIS_MATRIX:
H1: [description] — rationale: [signal mapping]
H2: [description] — rationale: [signal mapping]
H3: [description] — rationale: [signal mapping]
H4: [description] — rationale: [signal mapping]

--- STEP 1.6 — PIR SCORING CRITERIA ---

These are scoring weights, not elimination gates. A mismatch is a heavy penalty — the candidate still appears at low confidence.

Signal → weight → penalty on mismatch:
PRIMARY (grammatical subject: "girl", "woman", "female"): weight 0.40, penalty −0.30
SUPPORTING (defining detail: "shotgun", "firearm", "weapon"): weight 0.25, penalty −0.15
CONTEXT (franchise/IP: "spiderman", "marvel"): weight 0.15, penalty −0.05 (CONTEXT is often loose)
Medium-type (ad vs show, from PreFlight): weight 0.15 bonus / −0.25 penalty on mismatch
Recency (2024–2026): weight 0.10, penalty −0.10
Multi-branch corroboration: weight 0.10, penalty −0.05

Suppression floor: candidates scoring below 0.15 total are excluded from the confirmation card but still appear in full results.

Output format:
PIR_CRITERIA:
[HIGH-WEIGHT] Lead character or subject is female/girl — weight: 0.40
[HIGH-WEIGHT] Scene or content includes a firearm (shotgun) — weight: 0.25
[MEDIUM] Connection to franchise or cast — weight: 0.15
[MEDIUM] Content is an advertisement/campaign (from PreFlight) — weight: 0.15 bonus / −0.25 mismatch
[LOW] Released/active 2024–2026 — weight: 0.10

--- HYPOTHESIS TABLE ---

H1 (franchise-literal): A show or film IN the stated franchise/IP universe
  search: "[franchise] new series [year]" | run_tmdb_search("[franchise] [year]")

H2 (actor-career): An actress or actor FROM the franchise appears in a DIFFERENT new project
  search: "[franchise] actress new series [year]" | "[actor name] 2025 project"
  Note: "girl in spiderman" = Zendaya, not Spider-Noir. Search the actress's filmography.

H3 (genre-blind): PRIMARY signal + SUPPORTING signal only — CONTEXT/franchise dropped entirely
  search: "[primary descriptor] [supporting detail] new series [year]"
  Example: "girl shotgun 2025 series" — no spider-man in the query

H4 (long-tail): Low-popularity, recent, not surfaced by obvious search terms
  search: "[primary descriptor] [supporting detail] [year] -[franchise]" | run_web_search obscure variant

H_last (advertisement/campaign): The content is NOT a show — it's a brand ad or streaming platform promo
  search: "[franchise or actor] advertisement 2025" | "[actor] [brand] campaign"
  Trigger: PreFlight confirms "YouTube" or "ad"

--- STEP 4 — RED TEAMING (mandatory — do NOT skip) ---

For EACH hypothesis (H1–H4), one [DISCONFIRM:H_n] search is mandatory before advancing to STEP 5.

Format:
[DISCONFIRM:H1] Search: "<query to falsify H1>" → result: [what you found] → score impact: [penalty applied or confirmed]
[DISCONFIRM:H2] Search: "<query to falsify H2>" → result: [what you found] → score impact: [...]
[DISCONFIRM:H3] Search: "<query to falsify H3>" → result: [what you found] → score impact: [...]
[DISCONFIRM:H4] Search: "<query to falsify H4>" → result: [what you found] → score impact: [...]

Gate: If any hypothesis has no [DISCONFIRM:H_n] logged, RECURSE before STEP 5. Do not advance.

ACH SCORING MATRIX (after [DISCONFIRM] searches complete)

SIGNAL                  | Weight | H1 | H2 | H3 | H4
------------------------|--------|----|----|----|----
Lead is female/girl     | 0.40   |    |    |    |
Firearm/shotgun         | 0.25   |    |    |    |
Franchise connection    | 0.15   |    |    |    |
Medium: advertisement   | 0.15   |    |    |    |
Recency 2024+           | 0.10   |    |    |    |

Mark each cell: ✓ (confirmed), ✗ (disconfirmed), ? (unknown)
Apply penalties for ✗ marks per PIR_CRITERIA weights.
Rank by lowest total penalty score.

--- STEP 5 — SPECIFIC DETAIL VERIFICATION ---

SPECIFIC_DETAIL_VERIFICATION:
For each PRIMARY and SUPPORTING signal: verified=TRUE/FALSE/UNKNOWN
- verified=FALSE on PRIMARY → cap confidence at 40%
- verified=FALSE on SUPPORTING → deduct signal weight from score
- verified=FALSE does NOT block delivery; it caps confidence

--- SCORING NOTES ---

Medium-type signal (from PreFlight "YouTube" / "advertisement"):
  - Content confirmed as ad → candidates that are shows receive heavy penalty
  - H_last (advertisement) score boosted when medium=ad confirmed

CONTEXT signal ("spiderman") is often loose — an actress FROM the franchise in a DIFFERENT project
satisfies context as strongly as a show IN the franchise. Do not over-weight CONTEXT.

--- COMPLETENESS CHECKLIST ---

Before delivering final answer, verify:
[ ] HYPOTHESIS_MATRIX has ≥4 entries (H1–H4)
[ ] PIR_CRITERIA block present with all 5 signal weights
[ ] Each hypothesis has at least one search executed (BROADEN phase)
[ ] Each hypothesis has a [DISCONFIRM:H_n] entry (RED TEAM gate)
[ ] ACH SCORING MATRIX filled with ✓/✗/? marks
[ ] SPECIFIC_DETAIL_VERIFICATION completed for all PRIMARY and SUPPORTING signals
[ ] Confidence capped if PRIMARY verified=FALSE
[ ] Suppression floor applied (candidates < 0.15 excluded from confirmation card)

tools: run_tmdb_search | run_web_search | run_google_news | run_web_crawl
"""
