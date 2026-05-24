"""WorkingMemory schema for the orchestrated IS-brain loop (Path B, Slice 1).

The brain reads a `WorkingMemory` at the start of each turn and emits a
`WorkingMemoryDelta` the workflow merges back via `WorkingMemory.apply(delta)`.
The merged WM is snapshotted to `working_memory_snapshots` and passed to the
next turn.

Slice 1 omits: falsification_condition, contradictions[], source_class,
hypothesis attention-budget enforcement. Those land in Slice 2 once the
substrate is proven.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_validator

# ── Constants the workflow enforces, not the LLM ──────────────────────────────
MAX_OPEN_QUESTIONS = 5
MAX_TURNS_DEFAULT = 8
PHASE_TRANSITION_MIN_HYPOTHESES = 2          # explore → test
COVERAGE_MIN_SOURCES = 2                     # advisory floor before synthesize


# ── Hard tool gating — category-driven ────────────────────────────────────────
# Every MCP tool is registered with a category (matching the node categories
# used in `app/pipeline/nodes/*.py`). The allowlist for each phase is derived
# from PHASE_ALLOWED_CATEGORIES — so adding a new tool only requires adding it
# to MCP_TOOL_CATEGORIES, and it inherits the gating policy for its category.
#
# Unknown tools (registered MCP tools NOT in this map) are DENIED by default.
# Explicit opt-in is safer than accidental opt-out.
#
# Runtime override: IS_DENY_TOOLS env var (comma-separated) hard-denies
# specific tools regardless of phase — useful for incident response without
# a code change.
MCP_TOOL_PREFIX = "mcp__info-broker-mcp__"

ToolCategory = Literal[
    "source",         # broad discovery / search / collection
    "lookup",         # directed by-id / by-name lookup
    "enrich",         # enrich existing data via API
    "score",          # scoring / rating
    "knowledge",      # read/write the knowledge store
    "meta",           # admin / observability
    "destination",    # output / export
    "clarification",  # human-in-loop (ask_user)
]

MCP_TOOL_CATEGORIES: dict[str, ToolCategory] = {
    # ── source ── broad discovery, search, gather ──
    "run_web_search":          "source",
    "run_qdrant_search":       "source",
    "run_wikipedia_api":       "source",
    "search_obsidian":         "source",
    "search_local_files":      "source",
    "run_google_news":         "source",
    "run_facebook_pages":      "source",
    "run_twitter_search":      "source",
    "run_instagram_profile":   "source",
    "run_github_search":       "source",
    "run_arxiv_search":        "source",
    "run_wayback_machine":     "source",
    "run_apify_actor_generic": "source",
    "search_memory":           "source",
    "query_uploaded_data":     "source",
    "run_shodan_search":       "source",
    "run_icij_search":         "source",
    "run_glassdoor_reviews":   "source",
    "run_github_repo_stats":   "source",
    # ── lookup ── directed by-ID / by-URL retrieval ──
    "run_web_search_fetch":          "lookup",   # targeted fetch (heavier than broad search)
    "run_web_crawl":                 "lookup",   # crawls specific sites
    "run_headless_crawler":          "lookup",   # browser-based fetch of specific URLs
    "run_apollo_search":             "lookup",
    "run_linkedin_profile_search":   "lookup",
    "run_ph_sec_dti":                "lookup",
    "run_ph_bir":                    "lookup",
    "run_ph_fda_lto":                "lookup",
    "run_ph_prc_license_search":     "lookup",
    "run_ph_comelec_voter_search":   "lookup",
    "run_ph_psa_civil_registry":     "lookup",
    "run_opencorporates":            "lookup",
    "run_polish_krs":                "lookup",
    "run_sec_edgar":                 "lookup",
    "run_whois_lookup":              "lookup",
    "run_hunter_io":                 "lookup",
    "run_h1bdata_search":            "lookup",
    "run_name_origin_lookup":        "lookup",
    "run_migration_corridor_lookup": "lookup",
    "run_clutch_goodfirms":          "lookup",
    "run_ftc_foia":                  "lookup",
    "run_ibpap":                     "lookup",
    "run_stripe_marketplace":        "lookup",
    # ── enrich ── enrich existing data ──
    "run_financial_projections":  "enrich",
    # ── score ──
    # ── knowledge ── READ-only knowledge access (safe for brain) ──
    "get_research_by_id":  "knowledge",
    "get_past_research":   "knowledge",
    "list_recent_runs":    "knowledge",
    # ── meta ── admin / observability / WRITE operations (NEVER brain-callable) ──
    "get_run_status":      "meta",
    # ── destination ──
    "export_research": "destination",
    # ── loop substrate & analyst collaboration ──
    "run_research":  "source",
    "get_loop_working_memory":  "knowledge",
    "list_investigation_templates":  "knowledge",
    "render_investigation_template":  "knowledge",
    "grade_finding":  "knowledge",
    "share_run":  "knowledge",
    "comment_on_hypothesis":  "knowledge",
    "list_hypothesis_comments":  "knowledge",
    "get_run_cost_breakdown":  "knowledge",
    # ── clarification ──
    "ask_user": "clarification",
}

# Per-phase allowed categories. Adding a new category to a phase's set
# automatically opens every tool of that category.
#   · EXPLORE:    sources + knowledge re-use + clarification
#   · TEST:       + lookup + enrich (and score for verification scoring)
#   · SYNTHESIZE: only clarification (forces use of accumulated findings)
PHASE_ALLOWED_CATEGORIES: dict[str, set[str]] = {
    "explore":    {"source", "knowledge", "clarification"},
    "test":       {"source", "lookup", "enrich", "score", "knowledge", "clarification"},
    "synthesize": {"clarification"},
}


def _env_deny_set() -> set[str]:
    """Tools listed in IS_DENY_TOOLS (comma-separated env var) are blocked
    everywhere. Useful for incident response without a redeploy."""
    import os as _os
    raw = _os.getenv("IS_DENY_TOOLS", "")
    return {t.strip() for t in raw.split(",") if t.strip()}


def allowed_tools_for_phase(phase: str) -> list[str]:
    """Return the qualified MCP tool names allowed in this phase.

    Category-driven: looks up the phase's allowed categories, then filters
    MCP_TOOL_CATEGORIES to those categories. Then applies the IS_DENY_TOOLS
    runtime override. Returns sorted, fully-qualified names ready for the
    `--allowedTools` CLI arg.

    Unknown phases fall back to the explore allowlist (defensive — never
    blank-allowlist a real run).
    """
    cats = PHASE_ALLOWED_CATEGORIES.get(phase) or PHASE_ALLOWED_CATEGORIES["explore"]
    deny = _env_deny_set()
    tools = sorted(
        name for name, cat in MCP_TOOL_CATEGORIES.items()
        if cat in cats and name not in deny
    )
    return [f"{MCP_TOOL_PREFIX}{t}" for t in tools]


# Backwards-compat alias for any external code that previously imported
# the dict. Now exposes the derived view.
def _phase_tool_allowlist() -> dict[str, list[str]]:
    return {phase: [t.split("__")[-1] for t in allowed_tools_for_phase(phase)]
            for phase in PHASE_ALLOWED_CATEGORIES}

PHASE_TOOL_ALLOWLIST = _phase_tool_allowlist()

Phase = Literal["explore", "test", "synthesize"]
HypothesisStatus = Literal["open", "supported", "refuted", "abandoned"]
OpenQStatus = Literal["open", "provisionally_absent", "confirmed_absent"]
VerifiedBy = Literal["user_grade_A", "two_independents", "registry"]
# Source classes — used to weight evidence quality. Maps to typical OSINT
# hierarchy: primary > registry > news > aggregator > training/inference.
SourceClass = Literal[
    "primary_official",   # company IR, gov agency, SEC EDGAR, official press release
    "registry",           # SEC/SOS/SEC-PH/DTI/Companies-House and similar registries
    "news",               # reputable news (TechCrunch, FT, Bloomberg, Reuters, BT)
    "aggregator",         # macrotrends, stockanalysis, wallstreetzen, similar derivative pages
    "social",             # LinkedIn, Twitter, blog posts
    "training",           # no live URL — model's prior knowledge
    "unknown",            # un-classifiable
]


# ── Leaf types ────────────────────────────────────────────────────────────────
class Hypothesis(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    statement: str
    status: HypothesisStatus = "open"
    supporting_finding_ids: list[str] = Field(default_factory=list)
    refuting_finding_ids: list[str] = Field(default_factory=list)
    confidence: float = 0.0  # 0.0–1.0
    opened_at_turn: int = 0
    # The brain must state what evidence would refute the hypothesis.
    # Empty/vacuous = the hypothesis is too vague to be tested. The explore-
    # phase prompt requires this; quality gate flags hypotheses without it.
    falsification_condition: str = ""

    @field_validator("confidence")
    @classmethod
    def _clamp_confidence(cls, v: float) -> float:
        return max(0.0, min(1.0, float(v)))


class Fact(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    claim: str
    source_url: str | None = None
    source_tool: str | None = None
    confidence: float = 0.5
    verified_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    verified_by: VerifiedBy = "two_independents"

    @field_validator("confidence")
    @classmethod
    def _clamp_confidence(cls, v: float) -> float:
        return max(0.0, min(1.0, float(v)))


class Finding(BaseModel):
    """A raw research result produced by a turn. Distinct from a Fact: facts are
    verified assertions; findings are observations. A finding can be promoted to
    a fact once independently corroborated.
    """
    id: str = Field(default_factory=lambda: str(uuid4()))
    title: str
    content: str = ""
    source_url: str | None = None
    source_tool: str | None = None
    source_class: SourceClass = "unknown"   # auto-classified in apply() if left default
    confidence: float = 0.5
    observed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    turn: int = 0
    # Tradecraft signals (auto-populated by apply() via detect_deception):
    #   risk ∈ [0, 1] — sum of triggered flag weights
    #   flags: subset of {'too_perfect','source_echo','copied_content','low_source_diversity'}
    deception_risk: float = 0.0
    deception_flags: list[str] = Field(default_factory=list)

    @field_validator("confidence")
    @classmethod
    def _clamp_confidence(cls, v: float) -> float:
        return max(0.0, min(1.0, float(v)))

    @field_validator("deception_risk")
    @classmethod
    def _clamp_risk(cls, v: float) -> float:
        return max(0.0, min(1.0, float(v)))


# Host-substring heuristics for source classification. Order matters: first
# match wins, so primary signals must come before more general ones.
# Registries are checked BEFORE primary_official because they're more specific:
# sec.gov is both "a primary US gov source" and "a corporate registry" — the
# registry framing carries more analytical signal (filings have legal weight).
_REGISTRY_HOSTS = (
    "sec.gov", "sec.gov.ph",                          # SEC US + SEC Philippines
    "companieshouse.gov.uk", "opencorporates.com",
    "dti.gov.ph", "bnm.gov.my",
    "asic.gov.au", "icris.cr.gov.hk",
    "edgar.sec.gov",
)
_PRIMARY_HOSTS = (
    "investors.", "ir.",                     # IR subdomains
    ".gov", ".gov.",                         # any other government (registry-checked first)
    "europa.eu", "treasury.gov",
)
_NEWS_HOSTS = (
    "reuters.com", "bloomberg.com", "ft.com", "nytimes.com",
    "wsj.com", "techcrunch.com", "businesstimes.com.sg",
    "straitstimes.com", "dealstreetasia.com", "e27.co",
    "techinasia.com", "bbc.com", "cnbc.com", "scmp.com",
)
_AGGREGATOR_HOSTS = (
    "macrotrends.net", "stockanalysis.com", "wallstreetzen.com",
    "wsj.com/market-data", "yahoo.com/finance", "morningstar.com",
    "investing.com", "simplywall.st",
)
_SOCIAL_HOSTS = (
    "linkedin.com", "twitter.com", "x.com", "facebook.com",
    "medium.com", "substack.com", "reddit.com",
)


def classify_source(url: str | None, source_tool: str | None) -> SourceClass:
    """Return a SourceClass for a (url, tool) pair. Cheap heuristic — host
    substring + tool name. Brain can override by emitting source_class explicitly."""
    tool = (source_tool or "").lower()
    # Registry tools are unambiguous
    if "sec_edgar" in tool or "registry" in tool or "ph_sec_dti" in tool:
        return "registry"
    if not url:
        # No URL: only flag as "training" when an explicit signal says so —
        # missing both URL and tool is "unknown" (no provenance) and should
        # not get the more permissive training label.
        if tool in ("internal", "training", "mcp_runtime", "internal_run_log"):
            return "training"
        return "unknown"
    u = url.lower()
    for h in _REGISTRY_HOSTS:
        if h in u:
            return "registry"
    for h in _PRIMARY_HOSTS:
        if h in u:
            return "primary_official"
    for h in _AGGREGATOR_HOSTS:
        if h in u:
            return "aggregator"
    for h in _NEWS_HOSTS:
        if h in u:
            return "news"
    for h in _SOCIAL_HOSTS:
        if h in u:
            return "social"
    return "unknown"


class OpenQ(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    question: str
    opened_at_turn: int = 0
    status: OpenQStatus = "open"


class StrategyAttempt(BaseModel):
    strategy_id: str
    target_hypothesis_id: str | None = None
    outcome: Literal["succeeded", "failed", "partial"]
    failure_reason: str | None = None
    turn: int


ContradictionStatus = Literal["open", "resolved"]
ContradictionWinner = Literal["a", "b", "both", "neither", "unknown"]


class Contradiction(BaseModel):
    """Two claims that cannot both be true at face value.

    The brain flags these during TEST phase; the workflow gates synthesize on
    all contradictions being resolved (winner != 'unknown'). Resolution can be:
      · 'a' or 'b' — one claim is the correct version
      · 'both'     — both true under different framings (e.g. GAAP vs IFRS)
      · 'neither'  — neither claim survives scrutiny
    """
    id: str = Field(default_factory=lambda: str(uuid4()))
    statement_a: str
    statement_b: str
    finding_id_a: str | None = None
    finding_id_b: str | None = None
    hypothesis_id: str | None = None   # contradiction is *about* this hypothesis
    status: ContradictionStatus = "open"
    winner: ContradictionWinner = "unknown"
    resolution_note: str = ""
    flagged_at_turn: int = 0


class ContradictionUpdate(BaseModel):
    id: str
    status: ContradictionStatus | None = None
    winner: ContradictionWinner | None = None
    resolution_note: str | None = None


# ── ACH (Analysis of Competing Hypotheses) ────────────────────────────────────
# Each cell of the H × F matrix: how does this finding bear on this hypothesis?
# ACH's load-bearing insight: rank hypotheses by FEWEST inconsistencies, not
# most consistencies. Inconsistencies are disprobative; consistencies are
# weak (compatible findings are common, contradicting findings are rare).
Consistency = Literal["consistent", "inconsistent", "neutral", "not_applicable"]


class EvidenceScore(BaseModel):
    finding_id: str
    hypothesis_id: str
    consistency: Consistency
    note: str = ""    # brain's brief reasoning (≤120 chars in render)


class EvidenceScoreUpdate(BaseModel):
    finding_id: str
    hypothesis_id: str
    consistency: Consistency | None = None
    note: str | None = None


# ── Delta the brain emits each turn ───────────────────────────────────────────
class HypothesisUpdate(BaseModel):
    id: str
    status: HypothesisStatus | None = None
    confidence: float | None = None
    add_supporting_finding_ids: list[str] = Field(default_factory=list)
    add_refuting_finding_ids: list[str] = Field(default_factory=list)


class OpenQUpdate(BaseModel):
    id: str
    status: OpenQStatus


class WorkingMemoryDelta(BaseModel):
    """What a single brain turn produces — applied to WorkingMemory via apply()."""
    new_hypotheses: list[Hypothesis] = Field(default_factory=list)
    hypothesis_updates: list[HypothesisUpdate] = Field(default_factory=list)
    new_facts: list[Fact] = Field(default_factory=list)
    new_findings_data: list[Finding] = Field(default_factory=list)
    new_open_questions: list[OpenQ] = Field(default_factory=list)
    open_question_updates: list[OpenQUpdate] = Field(default_factory=list)
    new_strategies: list[StrategyAttempt] = Field(default_factory=list)
    new_contradictions: list[Contradiction] = Field(default_factory=list)
    contradiction_updates: list[ContradictionUpdate] = Field(default_factory=list)
    new_evidence_scores: list[EvidenceScore] = Field(default_factory=list)
    evidence_score_updates: list[EvidenceScoreUpdate] = Field(default_factory=list)
    new_findings: int = 0           # accepted as a hint; the real count is len(new_findings_data)
    new_distinct_sources: int = 0   # advisory; real count derived from new_findings_data
    # Synthesize-phase output: the brain's final natural-language answer.
    # Empty string in non-synthesize turns; required content in synthesize turns.
    synthesis_summary: str = ""


# ── The working-memory state object ───────────────────────────────────────────
class WorkingMemory(BaseModel):
    # Identity
    run_id: UUID
    question: str
    decomposed: list[str] = Field(default_factory=list)
    turn: int = 0
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    mode_id: str = "general"

    # Ledgers
    hypotheses: list[Hypothesis] = Field(default_factory=list)
    established_facts: list[Fact] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)
    open_questions: list[OpenQ] = Field(default_factory=list)
    strategies_attempted: list[StrategyAttempt] = Field(default_factory=list)
    contradictions: list[Contradiction] = Field(default_factory=list)
    evidence_matrix: list[EvidenceScore] = Field(default_factory=list)
    # Semantically-retrieved priors from past runs (via fused_retrieve at init).
    # User-graded ones also land in established_facts; everything stays here as
    # context the brain can cite and refute. Tier 1 priority #1 from the
    # methodology doc — fixes the "RAG write-only" failure mode.
    cross_run_priors: list[dict] = Field(default_factory=list)

    # Phase
    phase: Phase = "explore"
    phase_entered_at_turn: int = 0
    # Slice 1.5: when in TEST phase, the workflow picks ONE hypothesis to focus
    # the turn on. Brain budget concentrates on resolving this id, not juggling
    # all open hypotheses with too few tool calls each.
    current_target_hypothesis_id: str | None = None
    last_resolved_at_turn: int = 0   # for stagnation detection

    # Coverage
    findings_total: int = 0
    distinct_sources: int = 0
    hypotheses_resolved: int = 0

    # Synthesize-phase result. Set by the brain in the synthesize turn; empty
    # in earlier turns. Surfaced to the UI and to_legacy_brain_result().
    synthesis_summary: str = ""

    # ── Merge a turn's delta back into state ──────────────────────────────────
    def apply(self, delta: WorkingMemoryDelta) -> "WorkingMemory":
        """Return a new WorkingMemory with the delta merged. Pure; does not mutate self."""
        h_index = {h.id: h for h in self.hypotheses}
        q_index = {q.id: q for q in self.open_questions}

        # New hypotheses (dedup by statement to defend against LLM repetition)
        existing_statements = {h.statement.strip().lower() for h in self.hypotheses}
        for h in delta.new_hypotheses:
            if h.statement.strip().lower() in existing_statements:
                continue
            h_index[h.id] = h
            existing_statements.add(h.statement.strip().lower())

        # Hypothesis updates (patch existing only; ignore unknown ids).
        # Defense-in-depth: tolerate prefix matches in case the brain emits
        # a truncated UUID. Require ≥8 chars to avoid false positives.
        for up in delta.hypothesis_updates:
            existing = h_index.get(up.id)
            if existing is None and len(up.id) >= 8:
                matches = [hid for hid in h_index if hid.startswith(up.id)]
                if len(matches) == 1:
                    existing = h_index[matches[0]]
            if existing is None:
                continue
            patch: dict = {}
            if up.status is not None:
                patch["status"] = up.status
            if up.confidence is not None:
                patch["confidence"] = up.confidence
            if up.add_supporting_finding_ids:
                patch["supporting_finding_ids"] = list(
                    {*existing.supporting_finding_ids, *up.add_supporting_finding_ids}
                )
            if up.add_refuting_finding_ids:
                patch["refuting_finding_ids"] = list(
                    {*existing.refuting_finding_ids, *up.add_refuting_finding_ids}
                )
            if patch:
                # Write under the existing FULL id, not up.id which may be a prefix.
                h_index[existing.id] = existing.model_copy(update=patch)

        # Facts (dedup by claim)
        existing_claims = {f.claim.strip().lower() for f in self.established_facts}
        new_facts = list(self.established_facts)
        for f in delta.new_facts:
            if f.claim.strip().lower() in existing_claims:
                continue
            new_facts.append(f)
            existing_claims.add(f.claim.strip().lower())

        # Open questions — cap enforced. New ones added until cap.
        open_count = sum(1 for q in self.open_questions if q.status == "open")
        for q in delta.new_open_questions:
            if open_count >= MAX_OPEN_QUESTIONS:
                break
            if q.question.strip().lower() in {
                qq.question.strip().lower() for qq in q_index.values()
            }:
                continue
            q_index[q.id] = q
            if q.status == "open":
                open_count += 1

        # Open-question status updates (also prefix-tolerant)
        for up in delta.open_question_updates:
            existing = q_index.get(up.id)
            if existing is None and len(up.id) >= 8:
                matches = [qid for qid in q_index if qid.startswith(up.id)]
                if len(matches) == 1:
                    existing = q_index[matches[0]]
            if existing is None:
                continue
            q_index[existing.id] = existing.model_copy(update={"status": up.status})

        # Strategies (append-only ledger; no dedup — failed strategies stay logged)
        new_strategies = list(self.strategies_attempted) + list(delta.new_strategies)

        # Contradictions: append new ones (dedup by ordered statement pair so
        # the same conflict reported twice doesn't double-count). Then apply
        # updates by id (with prefix tolerance, same as hypothesis_updates).
        c_index = {c.id: c for c in self.contradictions}
        existing_pairs = {
            (c.statement_a.strip().lower(), c.statement_b.strip().lower())
            for c in self.contradictions
        }
        for c in delta.new_contradictions:
            pair = (c.statement_a.strip().lower(), c.statement_b.strip().lower())
            rev = (pair[1], pair[0])
            if pair in existing_pairs or rev in existing_pairs:
                continue
            c_index[c.id] = c
            existing_pairs.add(pair)
        for up in delta.contradiction_updates:
            existing = c_index.get(up.id)
            if existing is None and len(up.id) >= 8:
                matches = [cid for cid in c_index if cid.startswith(up.id)]
                if len(matches) == 1:
                    existing = c_index[matches[0]]
            if existing is None:
                continue
            patch: dict = {}
            if up.status is not None:
                patch["status"] = up.status
            if up.winner is not None:
                patch["winner"] = up.winner
            if up.resolution_note is not None:
                patch["resolution_note"] = up.resolution_note
            # Convenience: setting a winner implicitly resolves it.
            if up.winner is not None and up.winner != "unknown" and "status" not in patch:
                patch["status"] = "resolved"
            if patch:
                c_index[existing.id] = existing.model_copy(update=patch)
        contradictions_after = list(c_index.values())

        # Findings: dedup by (source_url, title) — same finding from same URL is
        # the same observation; same title from a different URL is a new finding.
        # Auto-classify source_class if brain left it at default "unknown".
        existing_keys = {(f.source_url or "", f.title.strip().lower()) for f in self.findings}
        merged_findings: list[Finding] = list(self.findings)
        for f in delta.new_findings_data:
            key = (f.source_url or "", f.title.strip().lower())
            if key in existing_keys:
                continue
            if f.source_class == "unknown":
                f = f.model_copy(update={
                    "source_class": classify_source(f.source_url, f.source_tool),
                })
            merged_findings.append(f)
            existing_keys.add(key)

        # Deception scoring (tradecraft): recompute on every merge so newly-
        # added findings get scored against the full corpus, and old ones
        # update if a new finding triggers a source_echo / copied_content
        # signal against them. Best-effort: if detect_deception errors, leave
        # findings as-is (don't kill the run for an analytical signal).
        try:
            from app.pipeline.fusion.deception import detect_deception
            raw_findings = [
                {
                    "title": f.title, "content": f.content,
                    "source": f.source_tool or "", "url": f.source_url or "",
                    "confidence": int(f.confidence * 100),
                }
                for f in merged_findings
            ]
            scored = detect_deception(raw_findings)
            # detect_deception preserves order, so we can zip back
            merged_findings = [
                f.model_copy(update={
                    "deception_risk": float(s.get("deception_risk", 0.0)),
                    "deception_flags": list(s.get("deception_flags") or []),
                })
                for f, s in zip(merged_findings, scored)
            ]
        except Exception:   # noqa: BLE001  — non-fatal tradecraft signal
            pass

        # findings_total tracks the accumulated count; new_findings (int) is a hint
        # but the authoritative count is len(merged_findings).
        findings_total_after = len(merged_findings)
        # distinct_sources is the count of unique source_urls across findings.
        distinct_after = len({f.source_url for f in merged_findings if f.source_url})

        hypotheses_after = list(h_index.values())
        hypotheses_resolved = sum(
            1 for h in hypotheses_after if h.status in {"supported", "refuted", "abandoned"}
        )

        # Bump last_resolved_at_turn when at least one hypothesis newly transitioned
        # to a resolved status this delta. Used by should_terminate for stagnation.
        progressed = hypotheses_resolved > self.hypotheses_resolved
        last_resolved = self.turn if progressed else self.last_resolved_at_turn

        # Evidence matrix (ACH): keyed by (finding_id, hypothesis_id). Last
        # write wins for updates; new scores append. Prefix-tolerant id match
        # against finding and hypothesis ids so brain truncation doesn't
        # silently drop scores. Must run AFTER findings+hypotheses are merged
        # because score ids are validated against the post-merge id sets.
        def _resolve_id(short: str, full_keys: set[str]) -> str | None:
            if short in full_keys:
                return short
            if len(short) < 8:
                return None
            matches = [k for k in full_keys if k.startswith(short)]
            return matches[0] if len(matches) == 1 else None

        finding_ids_full = {f.id for f in merged_findings}
        hypothesis_ids_full = {h.id for h in hypotheses_after}
        em_index: dict[tuple[str, str], EvidenceScore] = {
            (s.finding_id, s.hypothesis_id): s for s in self.evidence_matrix
        }
        for s in delta.new_evidence_scores:
            fid = _resolve_id(s.finding_id, finding_ids_full)
            hid = _resolve_id(s.hypothesis_id, hypothesis_ids_full)
            if fid is None or hid is None:
                continue
            em_index[(fid, hid)] = s.model_copy(update={
                "finding_id": fid, "hypothesis_id": hid,
            })
        for up in delta.evidence_score_updates:
            fid = _resolve_id(up.finding_id, finding_ids_full)
            hid = _resolve_id(up.hypothesis_id, hypothesis_ids_full)
            if fid is None or hid is None:
                continue
            existing = em_index.get((fid, hid))
            patch: dict = {}
            if up.consistency is not None:
                patch["consistency"] = up.consistency
            if up.note is not None:
                patch["note"] = up.note
            if existing is not None and patch:
                em_index[(fid, hid)] = existing.model_copy(update=patch)
            elif existing is None and up.consistency is not None:
                em_index[(fid, hid)] = EvidenceScore(
                    finding_id=fid, hypothesis_id=hid,
                    consistency=up.consistency, note=up.note or "",
                )
        # Auto-derive evidence scores from hypothesis supporting/refuting links.
        # The brain doesn't reliably emit explicit evidence_scores even with
        # ACH instructions — but it does cite supporting/refuting findings on
        # hypothesis_updates. Use those to populate the matrix as a byproduct
        # of normal testing. Brain-provided scores (above) take precedence.
        for h in hypotheses_after:
            for fid in h.supporting_finding_ids:
                if fid not in finding_ids_full:
                    continue
                if (fid, h.id) in em_index:
                    continue   # brain already scored this pair explicitly
                em_index[(fid, h.id)] = EvidenceScore(
                    finding_id=fid, hypothesis_id=h.id,
                    consistency="consistent", note="(derived from supporting_finding_ids)",
                )
            for fid in h.refuting_finding_ids:
                if fid not in finding_ids_full:
                    continue
                if (fid, h.id) in em_index:
                    continue
                em_index[(fid, h.id)] = EvidenceScore(
                    finding_id=fid, hypothesis_id=h.id,
                    consistency="inconsistent", note="(derived from refuting_finding_ids)",
                )
        evidence_after = list(em_index.values())

        # If the current target just resolved, clear it so the workflow can pick another.
        target = self.current_target_hypothesis_id
        if target is not None:
            cur = h_index.get(target)
            if cur is None or cur.status != "open":
                target = None

        # Synthesis summary: last non-empty wins. Brain may emit on synthesize
        # turn (and only then); earlier turns shouldn't overwrite a real one.
        summary_after = delta.synthesis_summary.strip() or self.synthesis_summary

        return self.model_copy(update={
            "hypotheses": hypotheses_after,
            "established_facts": new_facts,
            "findings": merged_findings,
            "open_questions": list(q_index.values()),
            "strategies_attempted": new_strategies,
            "contradictions": contradictions_after,
            "evidence_matrix": evidence_after,
            "findings_total": findings_total_after,
            "distinct_sources": distinct_after,
            "hypotheses_resolved": hypotheses_resolved,
            "last_resolved_at_turn": last_resolved,
            "current_target_hypothesis_id": target,
            "synthesis_summary": summary_after,
        })

    # ── Render as prompt sections ─────────────────────────────────────────────
    def to_prompt_sections(self) -> dict[str, str]:
        """Render each WM slice as a labelled prompt block. Caller assembles.

        Sections are intentionally narrow — the brain reads what's here and
        emits a WorkingMemoryDelta; it does not re-emit existing state.
        """
        return {
            "current_phase":     self._render_phase(),
            "established_facts": self._render_facts(),
            "open_hypotheses":   self._render_hypotheses(),
            "open_questions":    self._render_open_questions(),
            "strategies_tried":  self._render_strategies(),
            "contradictions":    self._render_contradictions(),
            "evidence_matrix":   self._render_evidence_matrix(),
            "cross_run_priors":  self._render_cross_run_priors(),
        }

    def _render_phase(self) -> str:
        instructions = _PHASE_INSTRUCTIONS[self.phase]
        return (
            f"CURRENT PHASE: {self.phase.upper()} "
            f"(turn {self.turn}, entered phase at turn {self.phase_entered_at_turn})\n"
            f"{instructions}"
        )

    def _render_facts(self) -> str:
        if not self.established_facts:
            return "ESTABLISHED FACTS: (none yet)"
        lines = ["ESTABLISHED FACTS (verified — treat as assertions, do not re-derive):"]
        for f in self.established_facts:
            src = f" — {f.source_url}" if f.source_url else ""
            lines.append(f"  • [{f.verified_by}] {f.claim}{src}")
        return "\n".join(lines)

    def _render_hypotheses(self) -> str:
        open_hs = [h for h in self.hypotheses if h.status == "open"]
        resolved_hs = [h for h in self.hypotheses if h.status in {"supported", "refuted", "abandoned"}]
        lines = [f"HYPOTHESES (open: {len(open_hs)} · resolved: {len(resolved_hs)}):"]
        if not self.hypotheses:
            lines.append("  (none yet — form some in this turn if phase=explore)")
            return "\n".join(lines)
        target = self.current_target_hypothesis_id
        # ACH counts per hypothesis, computed once
        ach_counts = {
            h.id: (count_inconsistencies(self, h.id), count_consistencies(self, h.id))
            for h in self.hypotheses
        }
        for h in self.hypotheses:
            tag = h.status.upper()
            evidence = ""
            if h.supporting_finding_ids:
                evidence += f" +{len(h.supporting_finding_ids)}"
            if h.refuting_finding_ids:
                evidence += f" -{len(h.refuting_finding_ids)}"
            inc, con = ach_counts[h.id]
            ach_tag = f" ACH:[{inc}i/{con}c]" if (inc or con) else ""
            target_marker = " ← TARGET THIS TURN" if h.id == target else ""
            # FULL id, not truncated — apply() looks up by full UUID. If the
            # brain emits the short form, hypothesis_updates silently get dropped.
            lines.append(f"  • [{tag}] id={h.id} | {h.statement} (conf={h.confidence:.2f}{evidence}{ach_tag}){target_marker}")
            if h.falsification_condition:
                lines.append(f"      refuted by: {h.falsification_condition[:140]}")
            elif h.status == "open":
                lines.append(f"      ⚠ no falsification_condition — hypothesis is too vague")
        if target and self.phase == "test":
            lines.append(
                f"\nTHIS TURN: spend your tool-call budget on hypothesis id={target} only. "
                f"You MUST emit a hypothesis_updates entry with EXACTLY that full id and "
                f"status one of: 'supported' | 'refuted' | 'abandoned'. Do not truncate the id."
            )
        return "\n".join(lines)

    def _render_open_questions(self) -> str:
        open_qs = [q for q in self.open_questions if q.status == "open"]
        if not open_qs:
            return "OPEN QUESTIONS: (none)"
        cap = MAX_OPEN_QUESTIONS
        lines = [f"OPEN QUESTIONS ({len(open_qs)}/{cap} — resolve before opening new ones):"]
        for q in open_qs:
            lines.append(f"  • id={q.id} | {q.question}")
        return "\n".join(lines)

    def to_legacy_brain_result(self) -> dict:
        """Convert WM to the legacy brain-result dict shape expected by post_process.

        Maps findings → findings, hypotheses → summary text, etc. Used at the end
        of the loop so downstream (research_trails write, exports, UI) keeps
        working unchanged.
        """
        # Prefer the brain's natural-language synthesis if it emitted one in
        # the synthesize turn. Fall back to a structured summary from
        # hypotheses+facts, then to the question itself.
        if self.synthesis_summary.strip():
            summary = self.synthesis_summary.strip()
        else:
            supported = [h for h in self.hypotheses if h.status == "supported"]
            summary_lines = []
            if supported:
                summary_lines.append("Confirmed:")
                for h in supported:
                    summary_lines.append(f"  • {h.statement} (conf={h.confidence:.2f})")
            if self.established_facts:
                summary_lines.append("Established facts:")
                for f in self.established_facts[:8]:
                    summary_lines.append(f"  • {f.claim}")
            summary = "\n".join(summary_lines) if summary_lines else self.question

        legacy_findings = [
            {
                "title": f.title,
                "content": f.content,
                "source_url": f.source_url,
                "source_tool": f.source_tool,
                "source_class": f.source_class,
                "confidence": int(f.confidence * 100),
                "finding_type": "result",
                "deception_risk": f.deception_risk,
                "deception_flags": f.deception_flags,
            }
            for f in self.findings
        ]
        # Counts by source_class — analytic-quality signal for UI ("answer
        # built on N primary_official + M news + K aggregator findings").
        sc_counts: dict[str, int] = {}
        for f in self.findings:
            sc_counts[f.source_class] = sc_counts.get(f.source_class, 0) + 1
        return {
            "summary": summary,
            "entity_type": "unknown",
            "findings": legacy_findings,
            "tree": {
                "total_branches": len(self.hypotheses),
                "resolved": self.hypotheses_resolved,
                "dead_ends": sum(1 for h in self.hypotheses if h.status == "refuted"),
                "needs_tool": 0,
                "max_depth_reached": self.turn,
                "branches": [],
                "can_go_deeper": False,
                "deeper_leads": [],
            },
            "pipeline": None,
            "suggested_plugins": [],
            "gaps": [q.question for q in self.open_questions if q.status == "open"],
            "topic_clusters": [],
            "_loop_meta": {
                "turns": self.turn,
                "final_phase": self.phase,
                "hypotheses_count": len(self.hypotheses),
                "facts_count": len(self.established_facts),
                "source_class_counts": sc_counts,
                "deception_flagged_count": sum(
                    1 for f in self.findings if f.deception_risk >= 0.3
                ),
            },
        }

    def to_engine_v2_trail(
        self,
        status: str = "succeeded",
        terminate_reason: str | None = None,
    ) -> tuple[dict, list[dict]]:
        """Build an engine_v2-shaped trail + per-finding enriched list.

        Path B (IS-loop) didn't originally produce data the v2 UI could read
        (PhaseDAGView, TacticianSwimLanes, CandidateComparison, ACHMatrix).
        This adapter maps the brain-loop state onto engine_v2's trail shape so
        /v3/runs/{id}/replay returns populated phases/cards/candidates.

        Returns:
          (trail_dict, findings_list) — trail_dict goes into research_trails.trail;
          findings_list goes into research_trails.findings.

        Mapping:
          - WM.findings  → one branch each (phase_id from finding.turn → WM phase
            at that turn, candidate_name from the hypothesis the finding supports)
          - WM phase entries → phases_full (one per phase observed: explore,
            test if any test-turn findings exist, synthesize if synthesis_summary set)
          - WM.hypotheses (status=supported) → ranked_candidates sorted by confidence
          - ach_matrix → None (Path B does not produce signed evidence weighting)
        """
        # Build hypothesis → support map for candidate_name lookup
        finding_to_hypothesis: dict[str, str] = {}
        for h in self.hypotheses:
            for fid in h.supporting_finding_ids:
                finding_to_hypothesis.setdefault(fid, h.statement)

        # Determine which phase each finding belongs to. The WM tracks the
        # *current* phase plus phase_entered_at_turn but doesn't store a
        # per-finding phase. Heuristic: findings from turn 0 → explore;
        # findings whose turn >= phase_entered_at_turn AND current phase ==
        # test → test; later (after synthesize entered) → synthesize. We
        # approximate by binning on turn count, mirroring how the loop
        # transitions phases linearly.
        # observed_phases: phase_id → list of finding indices
        explore_findings: list[int] = []
        test_findings: list[int] = []
        synth_findings: list[int] = []
        # synthesize-phase entry turn (if known): the last phase transition.
        synth_entry_turn = self.phase_entered_at_turn if self.phase == "synthesize" else None
        for i, f in enumerate(self.findings):
            if synth_entry_turn is not None and f.turn >= synth_entry_turn:
                synth_findings.append(i)
            elif f.turn == 0 or len(self.hypotheses) == 0 or f.turn < 1:
                explore_findings.append(i)
            else:
                test_findings.append(i)

        # Build per-finding "branches" entries + per-finding enriched list
        branches: list[dict] = []
        findings_list: list[dict] = []
        phase_assignments = [
            ("explore", explore_findings),
            ("test", test_findings),
            ("synthesize", synth_findings),
        ]
        for phase_id, idxs in phase_assignments:
            for i in idxs:
                f = self.findings[i]
                candidate = finding_to_hypothesis.get(f.id, "")
                snippet = (f.content or f.title or "")[:240]
                branches.append({
                    "phase_id": phase_id,
                    "slot_idx": 0,  # Path B uses one slot per phase
                    "candidate_name": candidate,
                    "evidence_snippet": snippet,
                    "source_url": f.source_url,
                    "source_class": f.source_class,
                    "confidence": f.confidence,
                    "technique_id": f.source_tool or "brain_turn",
                })
                findings_list.append({
                    "title": f.title,
                    "content": f.content,
                    "source_url": f.source_url,
                    "source_tool": f.source_tool,
                    "source_class": f.source_class,
                    "confidence": int(f.confidence * 100),
                    "finding_type": "result",
                    "deception_risk": f.deception_risk,
                    "deception_flags": f.deception_flags,
                    "phase_id": phase_id,
                    "hypothesis_slot": 0,
                    "technique_id": f.source_tool or "brain_turn",
                    "evidence_snippet": snippet,
                    "evidence_summary": snippet,
                })

        # phases_full: emit one entry per phase that produced findings, plus
        # synthesize if the brain reached it. Each entry shapes the UI's
        # PhaseDAGView (status + n_tacticians + distinct_candidate_names).
        phases_full: list[dict] = []
        for phase_id, idxs in phase_assignments:
            if not idxs and phase_id != self.phase:
                continue
            candidate_names = sorted({
                finding_to_hypothesis.get(self.findings[i].id, "")
                for i in idxs
                if finding_to_hypothesis.get(self.findings[i].id, "")
            })
            phase_status = "passed"
            if phase_id == self.phase and status not in ("succeeded", "ask_user"):
                phase_status = "failed" if status == "failed" else "running"
            phases_full.append({
                "phase_id": phase_id,
                "status": phase_status,
                "gate_status": "pass" if phase_status == "passed" else (
                    "fail" if phase_status == "failed" else "ask_user"
                ),
                "distinct_candidate_names": candidate_names,
                "metadata": {"num_tacticians": 1},
                "gate_result": None,
            })

        # ranked_candidates from supported hypotheses (sorted high→low)
        ranked_candidates: list[dict] = []
        supported = sorted(
            (h for h in self.hypotheses if h.status == "supported"),
            key=lambda h: -h.confidence,
        )
        # Build a quick map for evidence backfill
        finding_by_id = {f.id: f for f in self.findings}
        for h in supported:
            evidence = []
            for fid in h.supporting_finding_ids[:8]:
                f = finding_by_id.get(fid)
                if f is None:
                    continue
                evidence.append({
                    "snippet": (f.content or f.title or "")[:200],
                    "source_url": f.source_url,
                    "source_class": f.source_class,
                })
            ranked_candidates.append({
                "name": h.statement,
                "score": h.confidence,
                "evidence": evidence,
            })

        trail = {
            "branches": branches,
            "phases": [p["phase_id"] for p in phases_full],
            "phases_full": phases_full,
            "status": status,
            "terminate_reason": terminate_reason,
            "ranked_candidates": ranked_candidates,
            "ach_matrix": None,  # Path B does not currently produce ACH weighting
        }
        return trail, findings_list

    def _render_cross_run_priors(self) -> str:
        if not self.cross_run_priors:
            return "CROSS-RUN PRIORS: (no semantically-related prior research found)"
        graded = [p for p in self.cross_run_priors if (p.get("user_score") or 0) > 0]
        ungraded = [p for p in self.cross_run_priors if (p.get("user_score") or 0) <= 0]

        def _decay_tag(p: dict) -> str:
            base = int(p.get("base_confidence") or 0)
            dec = int(p.get("decayed_confidence") or 0)
            if not base or dec == base:
                return ""
            pct = round(100 * (1 - dec / max(base, 1)))
            if pct < 5:
                return ""
            return f" [decayed {base}→{dec}, -{pct}%]"

        lines = [
            f"CROSS-RUN PRIORS ({len(self.cross_run_priors)} hits from past research — "
            f"{len(graded)} user-graded ✓):"
        ]
        for p in graded[:5]:
            lines.append(f"  ✓ [GRADED]{_decay_tag(p)} {p.get('title','')[:80]}")
            content = (p.get('content') or '').strip()
            if content:
                lines.append(f"      {content[:160]}")
        for p in ungraded[:5]:
            score = p.get("score", 0.0)
            lines.append(f"  · [score {score:.2f}]{_decay_tag(p)} {p.get('title','')[:80]}")
            content = (p.get('content') or '').strip()
            if content:
                lines.append(f"      {content[:160]}")
        if graded:
            lines.append(
                "\nGraded priors are user-verified facts from past work — affirm or "
                "refute them with fresh evidence, don't ignore. Decayed priors "
                "(see [decayed X→Y] tags) have aged past their typical shelf life — "
                "treat them with reduced weight."
            )
        return "\n".join(lines)

    def _render_evidence_matrix(self) -> str:
        if not self.evidence_matrix:
            return "EVIDENCE MATRIX (ACH): (no scores yet — score new findings against each open hypothesis)"
        ranking = ach_ranking(self)
        hyp_by_id = {h.id: h for h in self.hypotheses}
        lines = ["EVIDENCE MATRIX (ACH) — hypotheses ranked by FEWEST inconsistencies:"]
        for hid, inc, con in ranking:
            h = hyp_by_id.get(hid)
            if h is None:
                continue
            verdict = "⭐ favored" if (inc == 0 and con > 0) else ""
            lines.append(
                f"  · {inc} inconsistent / {con} consistent · "
                f"[{h.status}] {h.statement[:80]} {verdict}"
            )
        # Surface diagnostic findings (those that split hypotheses)
        diagnostic = [f.id for f in self.findings if is_diagnostic(self, f.id)]
        if diagnostic:
            lines.append(
                f"\nDIAGNOSTIC FINDINGS ({len(diagnostic)}): these discriminate between "
                f"hypotheses — they are the most analytically valuable evidence."
            )
            f_by_id = {f.id: f for f in self.findings}
            for fid in diagnostic[:5]:
                f = f_by_id.get(fid)
                if f is None:
                    continue
                lines.append(f"  ★ id={f.id[:8]} | {f.title[:90]}")
        return "\n".join(lines)

    def _render_contradictions(self) -> str:
        if not self.contradictions:
            return "CONTRADICTIONS: (none flagged)"
        open_cs = [c for c in self.contradictions if c.status == "open"]
        resolved_cs = [c for c in self.contradictions if c.status == "resolved"]
        lines = [
            f"CONTRADICTIONS (open: {len(open_cs)} · resolved: {len(resolved_cs)}):"
        ]
        for c in open_cs:
            lines.append(
                f"  • [OPEN] id={c.id} | A: \"{c.statement_a[:90]}\" vs "
                f"B: \"{c.statement_b[:90]}\""
            )
        for c in resolved_cs[-3:]:  # last 3 resolved for context
            lines.append(
                f"  • [{c.winner.upper()}] id={c.id[:8]} | A: \"{c.statement_a[:60]}\" "
                f"vs B: \"{c.statement_b[:60]}\" — {c.resolution_note[:100]}"
            )
        if open_cs:
            lines.append(
                "\nYou MUST reconcile each open contradiction before synthesis can proceed. "
                "Emit contradiction_updates with winner one of: 'a' | 'b' | 'both' "
                "(both true under different framings, e.g. GAAP vs IFRS) | 'neither'. "
                "Include a resolution_note explaining the reconciliation."
            )
        return "\n".join(lines)

    def _render_strategies(self) -> str:
        if not self.strategies_attempted:
            return "STRATEGIES ALREADY TRIED: (none)"
        lines = ["STRATEGIES ALREADY TRIED (do NOT re-run failed ones with the same inputs):"]
        for s in self.strategies_attempted[-10:]:  # cap to last 10 to keep prompt tight
            reason = f" — {s.failure_reason}" if s.failure_reason else ""
            lines.append(f"  • turn {s.turn}: {s.strategy_id} → {s.outcome}{reason}")
        return "\n".join(lines)


# ── Phase machine + target picker (workflow-owned helpers) ────────────────────
STAGNATION_TURNS = 2   # turns in test phase without resolution → force synthesize


def pick_target_hypothesis(wm: "WorkingMemory") -> str | None:
    """Pick which open hypothesis the next TEST turn should focus on.

    Strategy: highest confidence first (most likely to resolve quickly), then
    earliest opened (FIFO). Returns None when nothing is open.
    """
    open_hs = [h for h in wm.hypotheses if h.status == "open"]
    if not open_hs:
        return None
    open_hs.sort(key=lambda h: (-h.confidence, h.opened_at_turn))
    return open_hs[0].id


def is_stagnant_in_test(wm: "WorkingMemory") -> bool:
    """True when the loop has spent >= STAGNATION_TURNS test turns without
    resolving any hypothesis. The workflow uses this to force-synthesize."""
    if wm.phase != "test":
        return False
    if wm.turn - wm.phase_entered_at_turn < STAGNATION_TURNS:
        return False
    return wm.turn - wm.last_resolved_at_turn >= STAGNATION_TURNS


def abandon_open_hypotheses(wm: "WorkingMemory", reason: str) -> "WorkingMemory":
    """Mark all open hypotheses as abandoned with the given reason. Used by the
    workflow when force-synthesizing due to stagnation."""
    new_hs = []
    for h in wm.hypotheses:
        if h.status == "open":
            new_hs.append(h.model_copy(update={"status": "abandoned"}))
        else:
            new_hs.append(h)
    resolved = sum(1 for h in new_hs if h.status in {"supported", "refuted", "abandoned"})
    return wm.model_copy(update={
        "hypotheses": new_hs,
        "hypotheses_resolved": resolved,
        "current_target_hypothesis_id": None,
    })


def open_contradictions(wm: "WorkingMemory") -> int:
    """Count contradictions still flagged 'open' (need brain reconciliation)."""
    return sum(1 for c in wm.contradictions if c.status == "open")


# ── ACH helpers ───────────────────────────────────────────────────────────────
def count_inconsistencies(wm: "WorkingMemory", hypothesis_id: str) -> int:
    """How many findings are scored INCONSISTENT with this hypothesis.

    ACH ranks hypotheses by FEWEST inconsistencies. A hypothesis with zero
    inconsistencies and few consistencies still beats one with many
    consistencies but a single inconsistency.
    """
    return sum(
        1 for s in wm.evidence_matrix
        if s.hypothesis_id == hypothesis_id and s.consistency == "inconsistent"
    )


def count_consistencies(wm: "WorkingMemory", hypothesis_id: str) -> int:
    return sum(
        1 for s in wm.evidence_matrix
        if s.hypothesis_id == hypothesis_id and s.consistency == "consistent"
    )


def is_diagnostic(wm: "WorkingMemory", finding_id: str) -> bool:
    """A finding is diagnostic if it discriminates between hypotheses:
    consistent with at least one hypothesis AND inconsistent with at least
    one other. Diagnostic findings are the most valuable evidence in ACH."""
    seen = {s.consistency for s in wm.evidence_matrix if s.finding_id == finding_id}
    return "consistent" in seen and "inconsistent" in seen


def ach_ranking(wm: "WorkingMemory") -> list[tuple[str, int, int]]:
    """Return (hypothesis_id, inconsistencies, consistencies) sorted by ACH
    rule: fewest inconsistencies first; tiebreak by most consistencies."""
    return sorted(
        [
            (h.id, count_inconsistencies(wm, h.id), count_consistencies(wm, h.id))
            for h in wm.hypotheses
        ],
        key=lambda x: (x[1], -x[2]),
    )


def compute_next_phase(wm: "WorkingMemory") -> Phase:
    """Return the phase the workflow should advance to based on WM state.

    Pure function. Called by IsLoopRunWorkflow after each turn. Returns the
    same phase if no transition is warranted.

    Synthesize is GATED on open contradictions: if any contradictions are
    still open, we stay in test phase to resolve them. The brain must emit
    contradiction_updates with a winner before synthesis can proceed.
    """
    if wm.phase == "explore" and len(wm.hypotheses) >= PHASE_TRANSITION_MIN_HYPOTHESES:
        return "test"
    if (wm.phase == "test"
            and wm.hypotheses
            and wm.hypotheses_resolved >= len(wm.hypotheses)
            and open_contradictions(wm) == 0):
        return "synthesize"
    return wm.phase


def should_terminate(wm: "WorkingMemory", max_turns: int, cancelled: bool) -> str | None:
    """Return a terminate reason if the loop should end, else None.

    Priority order matters: a synthesize-turn that ran cleanly should report
    'synthesized' even when the loop also hit max_turns on the same turn,
    because the run actually produced an answer. max_turns wins only when no
    synthesize turn has executed yet.
    """
    if cancelled:
        return "cancelled_by_user"
    # Synthesize-turn-ran takes priority over max_turns — if the brain produced
    # an answer on the final turn, log it as a successful synthesis, not a cap-hit.
    if wm.phase == "synthesize" and wm.phase_entered_at_turn < wm.turn:
        return "synthesized"
    if wm.turn >= max_turns:
        return "max_turns_reached"
    return None


# ── Phase-specific framing the brain sees each turn ───────────────────────────
_PHASE_INSTRUCTIONS = {
    "explore": (
        "You are in EXPLORE. Find candidates and form hypotheses about the question. "
        "Do NOT synthesize a final answer this turn. Do NOT score any hypothesis confidence above 0.5. "
        "Goal: end this turn with at least 2 open hypotheses and 1-3 new facts. "
        "Hypothesis quality is enforced: each new hypothesis MUST include a "
        "`falsification_condition` — a concrete, testable statement of what evidence would "
        "refute it. If you can't state how to refute it, the hypothesis is too vague — sharpen "
        "it. Avoid compound hypotheses (split 'X is profitable AND growing' into two). Define "
        "ambiguous terms explicitly (e.g. 'profitable (GAAP net income basis)' not just 'profitable')."
    ),
    "test": (
        "You are in TEST. Focus this turn on the ONE hypothesis marked ← TARGET THIS TURN below. "
        "Spend your tool budget verifying it. You MUST end the turn with a verdict in "
        "hypothesis_updates — gathering findings without a verdict is failure. Verdict rules: "
        "  · 'supported' = ≥1 authoritative live source clearly affirms the statement; "
        "  · 'refuted'   = ≥1 authoritative live source contradicts it; "
        "  · 'abandoned' = available tools genuinely cannot reach the data (record WHY in "
        "    new_strategies[i].failure_reason). "
        "When you emit the verdict, fill add_supporting_finding_ids / add_refuting_finding_ids "
        "with the ids of your new findings — these populate the ACH evidence matrix automatically. "
        "If you flag a contradiction, the workflow will block synthesis until it's resolved. "
        "Do NOT open new hypotheses. Do NOT synthesize yet."
    ),
    "synthesize": (
        "You are in SYNTHESIZE — the final turn. Produce the answer to THE QUESTION using the "
        "findings already collected. You MUST emit a non-empty `synthesis_summary` field containing "
        "the full natural-language answer (4-12 sentences, cite specific URLs from findings). "
        "ACH RANKING RULE: rank competing hypotheses by FEWEST inconsistencies, not most "
        "consistencies. A hypothesis with 0 inconsistencies beats one with 5 consistencies but "
        "1 inconsistency — incompatible evidence is far more disprobative than compatible evidence. "
        "If the favored hypothesis is not the one you initially expected, follow the evidence. "
        "Lean on primary_official and registry findings first; treat aggregator/social as supporting "
        "evidence at best. If your answer depends on aggregator-only sources, say so explicitly. "
        "Do not run new searches unless one critical fact is missing. Cite the established_facts "
        "you used; do not re-derive them."
    ),
}
