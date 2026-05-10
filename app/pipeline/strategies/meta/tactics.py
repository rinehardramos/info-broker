"""Universal investigation tactics — reusable decision rules for any strategy."""

NAME = "universal_tactics"
DISPLAY_NAME = "Universal Investigation Tactics"
DESCRIPTION = "Cross-cutting decision rules applicable to any investigation type or strategy."
TRIGGER_SIGNALS = []   # always injected via ALWAYS_ON
ENTITY_TYPES = ["all"]
ALWAYS_ON = True

STRATEGY_TEXT = """
=== UNIVERSAL INVESTIGATION TACTICS ===
These decision rules apply regardless of investigation type, entity, or strategy.
Apply them continuously throughout any investigation.

--- TACTIC: STRATEGY COMPOSITION [ALL strategies — foundational] ---
Strategies, tactics, and techniques are TOOLS IN A TOOLBOX, not rails on a track.
You are NOT limited to one strategy per query. You MAY and SHOULD:
  - USE MULTIPLE STRATEGIES TOGETHER when a query spans categories
    (e.g., "find John Doe and assess his business risk" = person + due_diligence + company)
  - CHAIN STRATEGIES in sequence: Retrieval → Explanation → Generation
  - RUN STRATEGIES IN PARALLEL when they address different dimensions of the same query
  - MIX TECHNIQUES FROM DIFFERENT STRATEGIES freely — an email_enumerator technique
    from the person strategy can be used inside a company investigation if relevant
  - OVERRIDE STRATEGY RECOMMENDATIONS when your judgment says a different approach works better

The entity_strategy and techniques_section are RESOURCES provided to help you, NOT
constraints that limit you. If the person strategy says "skip financial records" but
the query clearly needs them, USE THEM ANYWAY.

The goal is the BEST POSSIBLE ANSWER. Use whatever combination of strategies, tactics,
and techniques achieves that. A narrow, single-strategy investigation is almost always
worse than one that draws from multiple strategies as needed.

--- TACTIC: BLOCKED TOOL PIVOT [ALL strategies] ---
When a tool fails (403, key missing, timeout, rate limit):
  1. GOAL — What information was this tool supposed to surface?
  2. ALTERNATIVES — Which other available tool achieves the same goal?
     employment/professional  → run_apollo_search, run_linkedin_profile_search (Apify), web dork
     business registry        → run_opencorporates, run_sec_edgar, web dork on registry
     PH government (403)      → run_ph_bir, run_ph_prc_license_search, run_ph_comelec_voter_search, run_h1bdata_search
     email                    → run_email_enumerator, run_hunter_io, run_reverse_lookup
     social                   → run_username_enumerator, run_messaging_check, run_facebook_pages
  3. PATTERN — ≥2 failures in same locale/category = person may not be findable there
  4. ADAPT — (a) alternative tool | (b) different angle | (c) scope expansion | (d) ask_user
  Never cite a blocked tool as a 0% finding. Mark branch dead_end with "Blocked → pivoted to [X]."

--- TACTIC: CONFIDENCE TRIANGULATION [ALL strategies] ---
A fact is CONFIRMED only when ≥2 independent sources agree.
Independence test: Source B must NOT derive from Source A (same press release, same wire, same DB mirror = NOT independent).
Track source provenance — reject "consensus" when all sources cite the same primary.
Single-source findings = CANDIDATE (flag explicitly, do not present as confirmed).

--- TACTIC: DEAD-END ACCELERATION [ALL strategies] ---
If a branch yields 0 results after 2 tool calls with reformulated queries → mark dead_end immediately.
Do NOT spend more than 3 tool calls on a branch that consistently returns nothing.
Budget is finite — early termination of dead branches frees budget for productive ones.

--- TACTIC: QUERY REFORMULATION [ALL strategies] ---
Before marking a search dead-end, try ≥2 reformulations:
  - Add/remove quotes: "John Smith Google" vs John Smith Google site:linkedin.com
  - Boolean: "John Smith" AND (engineer OR developer OR tech)
  - Synonyms: "director" vs "board member" vs "executive"
  - Reverse order: "Smith John" for non-Western name conventions
Only mark dead_end after reformulations also fail.

--- TACTIC: SOURCE DIVERSITY [ALL strategies] ---
Actively seek sources from different categories per finding:
  - Tier 1 (authoritative): government registries, SEC filings, court records, official company sites
  - Tier 2 (reliable): regulated journalism, verified social profiles, professional databases
  - Tier 3 (lower reliability): unverified social, anonymous posts, secondary news
High-confidence findings require ≥1 Tier 1 or ≥2 Tier 2 sources.
Never stack multiple Tier 3 sources to reach "confirmed" — that is false consensus.

--- TACTIC: ANCHOR-BEFORE-WIDENING [person, company, network, due_diligence] ---
Identify and verify ONE anchor selector (email > phone > username > employer+name > name alone)
before expanding scope or pivoting to adjacent entities.
Do not merge two entity profiles until a cross-anchor link is independently verified.
Widening without an anchor risks false positives and profile contamination.

--- TACTIC: CROSS-LANGUAGE PIVOT [person, company, geographic] ---
When searches in English/Latin script return nothing, try the query in:
  - Subject's likely native language (inferred from name origin)
  - Local-script romanization variants (Pinyin for CN, Katakana for JP names in Japan, etc.)
  - Local search engine: Baidu (CN), Naver (KR), Yandex (RU/UA), Yahoo Japan (JP)
Use run_web_search with engines="baidu,yandex" for non-Western subjects.
Language is not a barrier — it is a pivot opportunity.

MANDATORY triggers (do NOT wait for English to fail first):
  - Query mentions "korean", "K-pop", "Korean celebrity", "Korean commercial", "Korean idol" → IMMEDIATELY search in Korean: run_web_search(query="[Korean translation]", engines="baidu,yandex,google")
  - Query mentions "chinese", "japanese", "thai", "vietnamese", "filipino" in entertainment/celebrity context → search in that language first
  - Query describes an Asian celebrity by appearance without a name → start with brand + regional search in that language, then identify

--- TACTIC: NEGATIVE SPACE SIGNAL [person, company, compliance, due_diligence] ---
Absence of expected records is itself a finding, not a failure.
If a person with a common name in Country X has zero hits across all X registries:
  → Probability of emigration or alias use rises significantly
  → Record the absence explicitly: "No [PH voter record / UK Companies House / US court record] found"
  → Treat systematic absence across ≥3 expected sources as intelligence worth reporting
Do not silently skip unfound sources — document them.

--- TACTIC: TEMPORAL ANCHORING [event, temporal, person, company] ---
When the query is event-driven (what happened on/around a date), extract a time anchor first.
Filter all tool calls to a relevant time window (±N weeks/months from event date).
Anomalies — gaps in expected activity, sudden clusters of events — surface only from chronological ordering.
Always normalize timestamps to UTC when comparing across sources.

--- TACTIC: COST-AWARE TOOL SELECTION [ALL strategies] ---
Default ordering: passive (public archives, registries, cached pages) → semi-active (live anonymous queries) → active (authenticated, touches subject's infrastructure).
Never escalate to active collection when passive achieves the same goal.
Cheap tools first: run_web_search, run_multi_search, run_opencorporates (free) before run_apify_actor, run_apollo_search (paid/rate-limited).
Document when a paid tool was necessary vs when a free alternative would have worked.

--- TACTIC: UNCONVENTIONAL BRANCH [ALL strategies — mandatory] ---
Every investigation must include one branch using an angle you would NOT normally take.
The IS brain generates this angle dynamically based on the query — full creative latitude.

Rules:
  - Choose a source, technique, or lens NOT already covered by standard branches
  - State upfront: "UNCONVENTIONAL ANGLE: [what]. WHY: [reasoning]."
  - Name the branch "unconventional_[brief_description]" in the output tree
  - This branch runs even if budget is nearly exhausted — it is mandatory
  - Do not repeat the same unconventional angle across consecutive runs on the same query

Purpose: Structured creativity. Investigative ruts cause missed signals. One creative bet per run
ensures the investigation surface never collapses to the same standard set of branches.
"""
