# Persona Simulations — Honest Tool Ratings

Roleplayed evaluations of the Info-Broker tool against five real user archetypes. Each simulation runs a representative workflow end-to-end, exercises features A–H from the absorption suite, and rates utility *in vacuum* — without builder bias, scored on "would I miss this feature if you removed it tomorrow."

**Features evaluated**

| ID | Feature |
|---|---|
| A | Auto-generated headline per run |
| B | Cumulative entity knowledge + contradiction surfacing |
| C | Run diff view |
| D | Inline annotations on findings |
| E | Hypothesis cross-reference across runs |
| F | "Continue this thread" follow-up |
| G | User-level cost dashboard |
| H | Open-questions digest |

---

## 1. KYC / Enhanced Due-Diligence Analyst

**Persona.** Senior KYC analyst at a mid-size PH bank's EDD desk. 4–8 files/week on PEPs, high-risk corporates, adverse-media subjects. Existing stack: WorldCheck, Dow Jones RiskCenter, OpenCorporates, LinkedIn Sales Nav, SEC PH, Google. Deliverable: 6–12 page memo with sourced findings, risk rating, recommendation.

**Scenario.** EDD file on *Maridel Holdings Inc.*, flagged by transaction monitoring for circular flows with a SG entity. Verify beneficial ownership, PEP status, adverse media. Memo due Thursday.

| Feature | Score | Verdict |
|---|---:|---|
| A. Headline | 9 | First-glance value, biggest time save |
| B. Entity knowledge + contradictions | **10** | Killer feature — replaces a private spreadsheet, surfaces conflicts no vendor tool does |
| C. Run diff | 8 | Analyst's `git diff`; high value, low frequency |
| D. Annotations | 8 | Only valuable if surfaced in B & E |
| E. Hypothesis xrefs | 7 | Powerful pending retrieval precision |
| F. Continue thread | 8 | Fixes the dangling-thread problem |
| G. Cost dashboard | 3 | Wrong audience on this surface — manager widget |
| H. Open-questions digest | 6 | Weekly housekeeping; risk of becoming noise |

**Overall: 8/10.** The cross-run memory layer (B/C/E) is the only feature unavailable in incumbent vendor tools. WorldCheck has better data; it does not have memory of my own prior reasoning.

**Buy at $50/mo?** Yes, mostly for B. At $500/mo I'd want G killed and audit-export shipped first.

### Gaps that block 10/10 for this persona

1. **Audit-trail export (PDF with citations + annotations)** — EDD memos go to BSP regulators; must be reproducible.
2. **Negative-evidence as first-class fact** — "checked X, found nothing" lost today.
3. **Watchlist mode** — monthly re-run of a subject, alert on diff (cron + C combined).
4. **Per-claim "verify" affordance on headline** — without it, headline must be re-checked against full run.
5. **Annotation → contradiction propagation** — manual notes must auto-feed B.
6. **Retrieval-score transparency on E** — false matches in compliance work are worse than no matches.
7. **Open-questions aging + dismissal** to prevent inbox-rot.

---

## 2. Marketing Manager (Demand Gen)

**Persona.** Marketing manager at a 60-person B2B SaaS. Owns demand-gen budget (~$80k/qtr), reports to CMO. Decisions: channel mix, campaign themes, ICP refinement, competitive positioning. Existing stack: HubSpot, Clearbit, SimilarWeb, Crayon, Gong, LinkedIn Insights, an analyst on contract.

**Scenario.** Q3 planning. Need to (a) decide whether to double down on PH SMB or pivot to mid-market SEA, (b) understand what 3 closest competitors changed in messaging in the last 90 days, (c) brief the agency on a "category education" theme.

| Feature | Score | Verdict |
|---|---:|---|
| A. Headline | 8 | "Competitor X added 2 pricing tiers, dropped 'enterprise-only' language" — exactly the kind of pre-digested insight I'd otherwise wait on the analyst for |
| B. Entity knowledge + contradictions | 9 | Competitor tracking is *literally* repeated investigation of the same entities. Cumulative view is gold |
| C. Run diff | **9** | "What changed about Competitor X between April and now" is a question I ask weekly |
| D. Annotations | 5 | I don't live in the tool; I'd annotate in Notion |
| E. Hypothesis xrefs | 6 | I have hypotheses ("PH SMB is saturated") but I phrase them differently each time — retrieval will miss |
| F. Continue thread | 7 | Useful for "this competitor moved, what about the others" follow-ups |
| G. Cost dashboard | 5 | I care because I sign off on budget — but I want it in $$ not RU |
| H. Open-questions digest | 8 | "What I still don't know about my market" is a *strategic* artifact, not housekeeping |

**Overall: 7/10.** C is more important to me than to the analyst. B is still huge. The tool's bias toward "investigation" feels right for competitive intel but slightly off for *trend* questions ("is the PH SMB market growing?").

**Buy at $50/mo?** Yes. At $500/mo I'd hesitate without ROI metrics.

### Gaps that block 10/10 for this persona

1. **Time-series / trend mode** — competitive intel is recurring. I want a saved query that re-runs weekly and auto-diffs against the prior run.
2. **$ cost translation** — RU is meaningless to me; show dollars and a comparison to my analyst hours saved.
3. **Notion / Slack export of headlines** — my team lives outside the tool. Push, don't make me pull.
4. **Audience/segment as a first-class entity** — "PH SMB fintech" is the thing I track, not individual companies.
5. **Confidence labels on competitive claims** — "Competitor pricing changed" needs source-class transparency. Press release ≠ inferred from job posting.
6. **Open-questions digest grouped by strategic theme** ("pricing power", "category education") not by run.

---

## 3. Marketing Analyst (IC, supports the manager above)

**Persona.** Marketing analyst, 2 years experience, IC. Owns the *production* of the artifacts the manager consumes. 60% time on data pulls + briefs, 40% on ad-hoc questions ("what's the LinkedIn follower delta of our top 5 competitors this quarter?"). Existing stack: SQL, HubSpot, SimilarWeb, manual scraping, Google Sheets.

**Scenario.** Manager asks Monday morning: "I need a one-pager on competitor X's positioning shift, with sourced quotes, by Wednesday." Repeat × 3 competitors.

| Feature | Score | Verdict |
|---|---:|---|
| A. Headline | **10** | This *is* my one-pager's lede. I rewrite it in my voice and ship |
| B. Entity knowledge + contradictions | 9 | I'd already built a half-broken Google Sheet for this |
| C. Run diff | 9 | "What changed since last time" is 40% of my ad-hoc work |
| D. Annotations | 8 | I take notes constantly during research; in-tool annotation beats Sheets |
| E. Hypothesis xrefs | 7 | Useful for "did we already check this angle" |
| F. Continue thread | 9 | I context-switch between 3 competitors; thread-resume saves me re-orienting |
| G. Cost dashboard | 4 | Don't care, not my budget |
| H. Open-questions digest | 8 | The "what I owe the manager next" backlog |

**Overall: 9/10.** This is the persona the tool fits best. The analyst's work is *exactly* "repeated structured research with cumulative knowledge", which is what the tool's substrate is.

**Buy at $50/mo?** Instantly. At $500/mo I'd ask my manager to expense it.

### Gaps that block 10/10 for this persona

1. **One-click "export to brief"** — headline + top 5 findings + sources → docx/markdown. Currently I copy-paste.
2. **Source quote extraction** — A quote with attribution is the unit of value, not a finding-summary.
3. **Saved-search templates** — "Competitor positioning audit" is a recurring shape; let me parameterize.
4. **Side-by-side multi-entity comparison view** — I always ask the same questions across N competitors.
5. **Annotation tags / categories** — so D becomes filterable in B (e.g. "positioning", "pricing", "hiring signal").
6. **Citation density indicator on headline** — so I know if I can ship the lede as-is or need to verify.

---

## 4. GTM Engineer

**Persona.** GTM engineer at a 200-person B2B startup. Builds the bridges between marketing/sales tools, owns lead enrichment pipelines, scoring models, and the Clearbit/Apollo/n8n/Hightouch stack. Half code, half operations. Deliverable: enriched lead records flowing into HubSpot with a fit + intent score.

**Scenario.** Sales leadership says: "Our PH SMB inbound conversion dropped. Figure out why. Also, the ICP we're enriching against may be outdated — re-derive it from closed-won data."

| Feature | Score | Verdict |
|---|---:|---|
| A. Headline | 7 | Useful but I prefer to inspect the underlying data myself |
| B. Entity knowledge + contradictions | 8 | "What do we know about Account X" is a real question, but my source of truth is HubSpot |
| C. Run diff | 7 | I'd rather diff in code |
| D. Annotations | 4 | I annotate in Linear/Notion |
| E. Hypothesis xrefs | 6 | Cross-run memory is interesting but I want it as an API, not a UI |
| F. Continue thread | 6 | I script my follow-ups |
| G. Cost dashboard | 7 | I run pipelines; cost-per-enrichment is a metric I track |
| H. Open-questions digest | 6 | I track work in Linear |

**Overall: 6/10.** GTM engineers want *primitives*, not absorption surfaces. The investigation substrate is valuable; the UI is mostly in the way for this persona.

**Buy at $50/mo?** Only if there's a robust API/MCP surface. At $500/mo only with bulk pricing and a webhook layer.

### Gaps that block 10/10 for this persona

1. **First-class API/MCP surface for everything in the UI** — *every* feature should be a callable. (Partly true today; needs to be the headline value.)
2. **Bulk enrichment endpoint** — POST 500 accounts, get back enriched + scored, async webhook on completion.
3. **n8n / Hightouch / Zapier connectors** — meet me where I orchestrate.
4. **Confidence + source-class as structured fields**, not buried in prose findings.
5. **Idempotency keys on runs** — so my pipelines don't double-spend on retries.
6. **Cost-per-finding / cost-per-enrichment as a primary metric** — RU/run is the wrong unit.
7. **Webhooks on contradiction surfacing** — "tell my pipeline when an entity acquires conflicting facts" is a data-quality signal.

---

## 5. Leads Engineer (Outbound / Prospecting)

**Persona.** "Leads engineer" at a series-B B2B startup — sits between SDR ops and GTM eng. Builds and maintains prospect lists, owns deliverability, runs experiments on outbound segments. Stack: Apollo, Clay, Smartlead, Instantly, a personal Notion of "things I've tried."

**Scenario.** AE leadership wants 200 net-new accounts/week in the "PH/SG/MY fintech operations leaders" segment. Existing list saturated. Need to find net-new accounts AND validate the contact data.

| Feature | Score | Verdict |
|---|---:|---|
| A. Headline | 8 | "Top 12 accounts in segment, 3 already in CRM, 9 net-new" — useful summary |
| B. Entity knowledge + contradictions | 7 | Helpful but my truth source is the CRM |
| C. Run diff | 8 | "Net-new vs last week's batch" is the question every Monday |
| D. Annotations | 6 | I annotate in Clay/Apollo |
| E. Hypothesis xrefs | 5 | I don't reason in hypotheses, I reason in lists |
| F. Continue thread | 8 | "More like these" is my entire job |
| G. Cost dashboard | 6 | Cost-per-lead is a metric, but I want it benchmarked vs Apollo credits |
| H. Open-questions digest | 5 | Not how I think about work |

**Overall: 6.5/10.** Decent fit, but I'd want it shaped around *lists* and *segments*, not *runs* and *hypotheses*. The tool is investigation-shaped; lead-gen is list-shaped.

**Buy at $50/mo?** Yes if it integrates with Clay/Apollo. At $500/mo only with a per-lead cost competitive with Apollo+Clay combined (~$0.10–0.30 / enriched lead).

### Gaps that block 10/10 for this persona

1. **Segment as first-class object** — "PH/SG/MY fintech ops leaders" is a saved entity that runs against forever, not a one-off query.
2. **List output mode** — N rows of {company, contact, email, fit_score, evidence} ready to push to Clay/Smartlead.
3. **Dedup against CRM** — accept a list of existing account domains, return only net-new.
4. **Per-lead cost benchmark** vs Apollo credits.
5. **Deliverability flag** — "email pattern verified" / "MX checked" should be structured fields.
6. **Continue-thread → "more like these N"** with negative examples (these 3 weren't a fit; find others avoiding these patterns).
7. **Webhook into Smartlead/Instantly on list completion.**

---

## Cross-persona synthesis

### Universally high-value (≥8 in 4+ personas)
- **A. Headline** — pre-digested insight is a time save for every persona.
- **B. Entity knowledge + contradictions** — the most consistently valued feature.
- **C. Run diff** — recurring research benefits from change-detection.
- **F. Continue thread** — high frequency, low cost.

### Persona-dependent
- **D. Annotations** — value depends on whether the persona lives in the tool (analyst yes, manager/eng no).
- **E. Hypothesis xrefs** — high for hypothesis-driven personas (KYC analyst), low for list-driven personas (leads eng).
- **G. Cost dashboard** — wrong surface for most ICs; valuable for managers and pipeline operators with right framing.
- **H. Open-questions digest** — strategic value for managers, housekeeping for analysts, irrelevant for engineers who track work elsewhere.

### Cross-cutting gaps that block 10/10 across multiple personas

1. **Export / push, don't only pull** — Notion, Slack, docx, CSV, webhook. Every persona except KYC explicitly named this.
2. **Saved query templates / segments / watchlists** — recurring shapes deserve first-class objects. Named by KYC (watchlist), marketing mgr (weekly recurring), marketing analyst (template), GTM eng (pipeline), leads eng (segment).
3. **Cost in $ + per-unit benchmarks** — RU is internal nomenclature. Translate to dollars and to a unit the persona already buys (analyst-hours, Apollo credits, enrichment rows).
4. **Structured confidence + source class on every claim** — not just prose. Every persona is judging trustworthiness at glance; UI must support it.
5. **First-class API/MCP parity with the UI** — engineering personas insist on this; analysts benefit from it indirectly (their tooling will be built on it).
6. **Audit / brief export** — KYC needs regulator-grade, marketing analyst needs one-pager-grade. Same primitive, different templates.
7. **Negative evidence as a first-class fact** — "we checked and found nothing" matters to every persona; lost today.

### What this implies for roadmap priority

| Priority | Item | Reasoning |
|---|---|---|
| **P0** | Push / export surface (Slack, Notion, docx, webhook) | Cited unprompted by 4/5 personas |
| **P0** | Saved templates / segments / watchlists | Cited unprompted by 5/5 personas under different names |
| **P0** | Structured confidence + source-class fields on findings | Trust gate for every persona |
| **P1** | $-denominated cost + per-unit benchmarks on G | Fixes the only universally low-scoring feature |
| **P1** | Negative-evidence persistence | Quiet but pervasive gap |
| **P1** | First-class API parity (MCP already partial) | Unlocks engineering personas entirely |
| **P2** | Brief / audit export templates | Unblocks compliance + marketing artifact workflows |
| **P2** | Side-by-side multi-entity comparison | Recurring shape across marketing personas |
| **P2** | Annotation tagging + propagation into B | Closes the D→B feedback loop |
| **P3** | Open-questions aging + dismissal | Stops H from becoming noise |
| **P3** | Retrieval-score transparency on E | Reduces false matches in compliance work |

### The honest one-line summary

The tool's substrate (cross-run memory + contradiction surfacing) is genuinely differentiated. The absorption layer (A–H) is *mostly* the right shape but the UI assumes the user lives inside it. Personas who don't (managers, engineers) need *export* and *API*; personas who do (analysts) need *templates* and *audit*. The lowest-hanging shift from 7–8 to 9–10 across all personas is push/export and saved-shape primitives, not new analytical features.
