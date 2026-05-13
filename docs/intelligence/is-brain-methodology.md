# IS Brain Intelligence Methodology
## A Living Research Document

> **Version:** 1.0 — 2026-05-10  
> **Status:** Initial — based on case analysis and Opus brainstorm sessions  
> **Next review:** When updated SAT literature, nation-state playbook research, or significant failure post-mortems are available  
> **Purpose:** Document learnings from IS brain failure analysis, human analyst gap audit, and hybrid architecture design. To be updated as research matures.

---

## Table of Contents

1. [How This Document Was Created](#provenance)
2. [Failure Post-Mortems That Triggered This Research](#failures)
3. [The Core Problem: Inverted Research Posture](#core-problem)
4. [Complete Intelligence Cycle for IS Brain](#intelligence-cycle)
5. [Structured Analytic Techniques (SATs) — Coverage Map](#sats)
6. [Human Analyst vs IS Brain — Gap Registry](#gap-registry)
7. [Fundamental Gaps — Design Around Not Close](#fundamental-gaps)
8. [The Hybrid Human-AI Architecture](#hybrid-architecture)
9. [Philippine-Specific Intelligence Considerations](#ph-specific)
10. [Implementation Priorities](#priorities)
11. [References and Further Research](#references)
12. [Changelog](#changelog)

---

<a name="provenance"></a>
## 1. How This Document Was Created

This document synthesizes learnings from:
- **Case analysis**: Post-mortems on two failed IS brain runs (Dyson/Wan Young commercial, Amazon 2026 ad)
- **Brainstorming sessions**: Multiple rounds with Claude Opus analyzing failure patterns
- **Intelligence tradecraft literature**: CIA ACH methodology (Richards Heuer), ICD 203 analytic standards, Sherman Kent estimative language, Bellingcat OSINT methodology, ODNI Structured Analytic Techniques
- **Domain expertise gap analysis**: Systematic audit of where a trained human intelligence analyst outperforms the current brain

All findings are based on the current state of the IS brain as of 2026-05-10. Many gaps are closable; some are fundamental to current LLM limitations.

---

<a name="failures"></a>
## 2. Failure Post-Mortems That Triggered This Research

### Case A: Dyson/Wan Young Commercial
- **Query**: User saw a person in a Dyson advertisement, wanted identification
- **Brain's failure**: Used training knowledge to guess Dyson brand ambassadors; never applied BRAND-FIRST strategy (Dyson → campaign → ambassador → person)
- **Root cause**: Tunnel vision on training data; strategy library existed but was not executed

### Case B: Amazon 2026 Promotional Ad (`run_id: 65dc9e39`)
- **Query**: "new series with girl in spiderman where man has a shotgun and looks like gritty action or drama?"
- **Correct answer**: Amazon Prime Video 2026 promotional advertisement — a composite reel featuring multiple upcoming titles including Spider-Noir (Nicolas Cage, shotgun, gritty 1930s noir) and a Zendaya project
- **Brain's answer**: The Last of Us Season 2 (Isabela Merced from Madame Web). 80-90% confidence. Zero actual tool calls — all from training knowledge.
- **Previous run** (`1392fde1`): Found Spider-Noir correctly as primary candidate (close, but framed as a single show rather than a promotional compilation). High-confidence findings indexed to Qdrant. Completely ignored 37 minutes later.

**Key failure cascade:**
1. Conflicting signals (Spider-Man actress + 1930s noir shotgun) not recognized as incompatible with a single show
2. No clarification triggered despite signal incoherence
3. Prior high-graded findings (A-grade Spider-Noir from `1392fde1`) sitting in Qdrant, never retrieved
4. Brain committed to a training-data hypothesis and confirmed it rather than testing it
5. Zero live tool calls for a "new series" query where training data is structurally outdated

**Pattern across both cases**: Tunnel vision on training knowledge → confirmation-seeking → premature conclusion without live verification.

---

<a name="core-problem"></a>
## 3. The Core Problem: Inverted Research Posture

### What the brain does
```
Training data hypothesis → seek confirmation → conclude
```

### What intelligence tradecraft requires
```
Cast wide (live) → enumerate hypotheses → test by elimination → narrow → conclude
```

**The manifestations:**
- Training knowledge treated as evidence, not as hypothesis fuel
- Branches corroborate the frontrunner instead of red-teaming it
- High confidence rewarded; uncertainty treated as failure
- Strategies are advisory, not binding — the brain improvises instead of executing its playbook
- No mandatory BROADEN phase before commitment

**The principle that must replace the current posture:**
> **Breadth before depth. Evidence before commitment. Live before training.**
> The brain's job is to execute a research plan, not to find an answer.
> An intelligence tool that improvises is a liability — unauditable and unreliable.

---

<a name="intelligence-cycle"></a>
## 4. Complete Intelligence Cycle for IS Brain

The following is the complete pre-research and research cycle derived from nation-state intelligence methodology, adapted for an OSINT context.

### Pre-Research Phase (currently missing almost entirely)

```
1.  PIR Definition              What must I answer? What constitutes "done"?
2.  Key Assumptions Check (KAC) What am I assuming before I start? Which 
                                 assumptions collapse the hypothesis if wrong?
3.  Bias Register Activation    Which cognitive biases am I most at risk of 
                                 for this query type?
4.  D&D Posture Decision        Should I assume the information environment 
                                 is being managed?
5.  Attribution Risk Assessment Which tools are safe to use? What footprints 
                                 would be left?
6.  Query Decomposition         What signals does this query contain? Are they 
                                 internally coherent?
7.  Coherence Check             Do all signals fit one known property? 
                                 If no → composite content hypothesis mandatory.
8.  Collection Management       Which tool is AUTHORITATIVE for each signal type?
9.  I&W Pre-commitment          What would I expect to find if H1/H2/H3 is true?
10. Grounding Pass              fused_retrieve() — what does the system already 
                                 know? Inject A-graded priors as assertions.
11. Clarification Gate          LLM judge (Haiku): does a residual gap remain 
                                 after grounding? PRIOR_CONFLICT ≥ 2 → ask user.
```

### Research Phase (partially implemented, not bound)

```
12. BROADEN                     Min 3 live tool calls. No commitment. Generate 
                                 widest possible hypothesis space from live evidence.
                                 Training knowledge generates candidate names only.
13. Hypothesis Enumeration      Structured list of 4-8 hypotheses with prior 
                                 source tags (live vs training_generated).
                                 ALWAYS include H_COMPOSITE for media sighting queries.
14. Evidence Matrix (ACH)       For each hypothesis × each evidence axis: 
                                 Consistent / Inconsistent / N/A. 
                                 Eliminate by inconsistency count, not corroboration.
15. KAC Mid-Research            Are working assumptions still holding after BROADEN?
16. Adversarial Branch          Structurally adversarial — goal is INCONSISTENCIES 
                                 with frontrunner, not supporting evidence.
                                 Minimum 3 disconfirming queries required.
17. COMMIT                      Deliberate, logged. Must cite ≥1 live source for 
                                 frontrunner. If cannot → escalate to clarification.
18. RECURSE                     Genuine hypothesis testing via ACH matrix.
                                 PoL deviation check on timeline data.
                                 SNA metrics computed if graph is built.
19. Replan Trigger              If new finding has evidence_lr ≥ 10 against 
                                 working hypothesis → tear down and rebuild.
20. All-Source Fusion           Resolve source conflicts by class hierarchy:
                                 primary_official > primary_judicial > 
                                 corroborated_secondary (2+ independent) > 
                                 single_secondary > primary_self > training_data
```

### Delivery Phase (partially implemented)

```
21. PIR Coverage Report         Which PIRs answered / partially answered / open
22. Strategy Coverage Report    Which strategies executed / skipped (with reason)
23. Source Class Breakdown      Distribution of sources by class
24. D&D Assessment              Final assessment of information environment integrity
25. Working Assumptions         Explicit list + fragility rating
26. Known Unknowns              Residual open questions + 3-state outcomes:
                                 found / provisionally_absent / confirmed_absent
27. Escalation Items            Human judgment required for: [list with blocking flag]
28. Audience-Calibrated Summary Executive / Legal / Operational / Journalistic
29. Estimative Language         ICD 203 standards: "almost certainly" / "likely" / 
                                 "we assess" / "possibly" mapped to confidence buckets
```

---

<a name="sats"></a>
## 5. Structured Analytic Techniques (SATs) — Coverage Map

Based on ODNI/CIA Structured Analytic Techniques handbook and Richards Heuer's "Psychology of Intelligence Analysis."

| SAT | Status | Notes |
|-----|--------|-------|
| **Analysis of Competing Hypotheses (ACH)** | Exists (`fusion/ach.py`) but not binding | Must become mandatory output contract |
| **Key Assumptions Check (KAC)** | Not implemented | Missing at both PLAN and mid-research |
| **Red Team / Devil's Advocacy** | Referenced but not structurally enforced | Adversarial branch exists in name only |
| **Team A / Team B** | Not implemented | Future: two independent brain runs on same query |
| **What If? Analysis** | Partial (falsifiers mentioned) | Not pre-committed at PLAN stage |
| **Brainstorming (structured)** | Partial (BROADEN phase proposed) | Not yet implemented |
| **Indicators Validation** | Not implemented | I&W pre-commitment not built |
| **Quality of Information Check** | Partial (`pyramid_scoring.py`) | Offline only, not binding |
| **Argument Mapping** | Not implemented | Could replace narrative branches |
| **Chronologies and Timelines** | Partial (findings have timestamps) | No event-velocity analysis |
| **Network / Link Analysis** | Partial (Neo4j exists) | SNA metrics not computed |
| **Pattern of Life Analysis** | Not implemented | No behavioral baseline framework |
| **Denial and Deception Analysis** | Exists (`fusion/deception.py`) | Offline, not active posture |
| **High Impact / Low Probability** | Not implemented | Tail risk analysis missing |
| **Cone of Plausibility** | Not implemented | Future scenario planning |
| **Cognitive Bias Checklist** | Not implemented | No active bias mitigation |
| **Estimative Language Standards** | Not implemented | ICD 203 not applied |
| **Source Typology / CRAAP** | Not implemented | No source class tagging |
| **Upstream Source Collapse** | Not implemented | 5 blogs citing 1 wire = 5 corroborations (wrong) |
| **Information Value Prioritization** | Not implemented | Tool ordering is arbitrary |
| **Query Decomposition** | Not implemented | No structured signal extraction |
| **Collection Management** | Not implemented | No tool-to-information-type mapping |
| **Priority Intelligence Requirements** | Not implemented | No PIR definition step |
| **Target System Modeling** | Not implemented | Facts collected, not system understood |
| **Social Network Analysis metrics** | Not implemented | Graph built but metrics not computed |
| **Satisficing vs. Optimizing** | Not implemented | Brain stops when "good enough" found |

**Coverage rate: approximately 4/25 SATs partially implemented, 0/25 binding.**

---

<a name="gap-registry"></a>
## 6. Human Analyst vs IS Brain — Gap Registry

*Assessed 2026-05-10. Closability: High = prompt/architecture change; Medium = requires new tooling or training; Low = partial; Fundamental = current LLM limitation.*

### A. Metacognition and Epistemic Calibration

| Gap | Closability | Implementation Direction |
|-----|-------------|--------------------------|
| A1. No "known unknowns" ledger | High | `open_questions` field in running state; DELIVER must enumerate resolved/unresolved/unasked |
| A2. Confidence is post-hoc not Bayesian | Medium | Discrete confidence buckets with hard rules; reject point estimates without basis |
| A3. No stop-and-replan on prior collapse | High | Prior-collapse event detector; evidence_lr ≥ 10 against working hypothesis → mandatory replan |

### B. Source Evaluation

| Gap | Closability | Implementation Direction |
|-----|-------------|--------------------------|
| B1. No source typology | High | `source_class` field per finding: primary_official / primary_self / secondary_news_t1 / secondary_news_t2 / ugc / aggregator / mirror |
| B2. CRAAP not applied | High | `published_at` + `inferred_currency`; reject findings >18mo for current-state claims without recent corroboration |
| B3. No upstream source collapse | Medium | Content-similarity dedup; count source clusters not URLs; integrate with `topic_clustering.py` |

### C. Cultural and Linguistic Intelligence

| Gap | Closability | Implementation Direction |
|-----|-------------|--------------------------|
| C1. No native-language search | High | Force translation of 2-3 highest-yield queries to Tagalog + regional language for PH context |
| C2. PH naming conventions | High | `name_variants_ph()` node: maiden, married, nickname, Hispanicized, Chinese-Filipino forms |
| C3. Local political/economic context | Medium | `app/knowledge/ph_political_economy.md` injected for PH locale investigations |
| C4. PH calendar context | Medium | PH government calendar knowledge file; flag actions on closure periods |

### D. Adversarial Awareness

| Gap | Closability | Implementation Direction |
|-----|-------------|--------------------------|
| D1. No managed information environment assumption | High | Adversarial-posture toggle for fraud/threat/due-diligence; D&D assessment mandatory |
| D2. No counter-curation branch | High | Mandatory for person investigations: archive.org diff, credential primary-source verification, absence checks |
| D3. No SEO-poisoning detection | Medium | `serp_anomaly_score`: domain recency + content reuse + anomalous ranking |
| D4. Attribution risk not tracked | Medium | Per-tool `attribution_risk` tag; accumulation → downshift to passive sources |

### E. Network and Relationship Reasoning

| Gap | Closability | Implementation Direction |
|-----|-------------|--------------------------|
| E1. Entities in flat findings list not a graph | High (Neo4j exists) | `relationship_graph` running state; inject current subgraph back into each RECURSE prompt |
| E2. No conspicuous-absence reasoning | High | For every primary-self claim, check where it would leave a record if true; `negative_space_check[]` in delivery |
| E3. No SNA metrics | High (Neo4j) | Betweenness, in-degree, clustering coefficient computed post-graph-build |
| E4. PH family/clan reasoning | Medium | PH political/business dynasty reference file; surname cross-check |

### F. Temporal Reasoning

| Gap | Closability | Implementation Direction |
|-----|-------------|--------------------------|
| F1. Snapshot not timeline | High | Mandatory Wayback diff for any subject domain; name-change/predecessor check for PH SEC entities |
| F2. No event-velocity analysis | High | Event-rate analyzer over corporate timeline; flag rates > population baseline |
| F3. Fixed reference frame | Medium | `reference_date` parameter; evaluate findings relative to it |

### G. Intuition and Anomaly Detection

| Gap | Closability | Implementation Direction |
|-----|-------------|--------------------------|
| G1. No red-flag pattern library | Medium | `red_flag_lexicon`: PH virtual-office addresses, stock photo signatures, templated copy fingerprints, scam language |
| G2. No cross-entity outlier detection | High (after E1) | Outlier detection once graph state exists |
| G3. Photo reuse detection not routine | High | Mandatory `run_face_search` + `run_exif_extractor` for person investigations with profile photo |

### H. Legal and Ethical

| Gap | Closability | Implementation Direction |
|-----|-------------|--------------------------|
| H1. No legal-obtainability tagging | High | Per-tool `legal_class`: public_record / tos_grey / leaked / paywalled_aggregated / pii_sensitive |
| H2. No PII handling discipline | High | PII redaction layer between findings → storage; PII visible only via authorized retrieval |
| H3. No chain of custody | High | Every tool call → archive copy + hash; findings reference hash |
| H4. No purpose-limitation gating | Medium | Per-investigation `purpose` field; per-tool `permitted_purposes` enforcement |

### I. Hypothesis Generation Quality

| Gap | Closability | Implementation Direction |
|-----|-------------|--------------------------|
| I1. Hypotheses template-shaped not generative | Medium | Mandatory adversarial hypothesis per investigation |
| I2. No falsifier pre-commitment | High | PLAN must emit `falsifiers[]`; RECURSE must search for them |
| I3. No case-archetype matching | Medium | `case_typologies.md`: fraud templates, scam patterns, shell-stack patterns |

### J. Communication and Reporting

| Gap | Closability | Implementation Direction |
|-----|-------------|--------------------------|
| J1. One report shape | High | `audience` parameter: executive / legal / operational / journalistic |
| J2. No estimative language | High | ICD 203 language mapped to confidence buckets; enforce in summary narrative |
| J3. No working assumptions disclosure | High | Mandatory `working_assumptions[]` in delivery |

### K. Memory and Case Continuity

| Gap | Closability | Implementation Direction |
|-----|-------------|--------------------------|
| K1. RAG read-side missing | High (infra exists) | `fused_retrieve()` before every brain launch; A-graded priors as assertions |
| K2. No salience decay | High (`decay.py` exists) | Bind decay to retrieval weights |
| K3. No case journal | High | Persist per-case: attempted hypotheses, discarded with reason, unpursued leads |

### L. Tool Judgment

| Gap | Closability | Implementation Direction |
|-----|-------------|--------------------------|
| L1. Block reason not interpreted as evidence | High | `block_taxonomy`: geo_block / paywall / auth_required / ratelimit / bot_block / target_takedown; each has evidentiary inference |
| L2. No tool-cost reasoning | High | Per-tool `cost_class` + `latency_class`; planner orders by cost-adjusted expected information gain |
| L3. No tool improvisation before suggest_plugin | High | Mandate 3 improvisation attempts (dorks, archive, lateral pivot) before escalating to suggest_plugin |

### M. Verification Standards

| Gap | Closability | Implementation Direction |
|-----|-------------|--------------------------|
| M1. Admiralty applied loosely | High | Per-finding `admiralty: {reliability, credibility, justification}`; reliability bound to source_class; credibility bound to post-collapse corroboration count |
| M2. No 2-independent-primary rule | High | Hard rule: confidence ≥ 80% requires ≥ 2 independent sources after upstream collapse, ≥ 1 primary_official |
| M3. Document vs. claim authenticity conflated | High | Separate `document_authenticity` and `claim_truth` scores per finding |

### N. Strategic Patience

| Gap | Closability | Implementation Direction |
|-----|-------------|--------------------------|
| N1. Brain optimizes for completion not wisdom | Medium | PIR completion criteria as hard stop condition |
| N2. No "stop pushing" on attribution risk | Medium | Tied to D4; passive-sources-only mode when risk accumulates |
| N3. Dead-end vs. confirmed-absent conflated | High | 3-state outcomes: found / provisionally_absent / confirmed_absent |

### O. Cross-Case Pattern Recognition

| Gap | Closability | Implementation Direction |
|-----|-------------|--------------------------|
| O1. Per-case isolation | Medium-High | BOOTSTRAP: embed + search prior cases for similar patterns; inject top-k matches |
| O2. No case clustering | Medium | Periodic entity-graph clustering across stored cases |

---

<a name="fundamental-gaps"></a>
## 7. Fundamental Gaps — Design Around, Not Close

These gaps are intrinsic to current LLM capabilities. The hybrid architecture (Section 8) routes these to human analysts.

### F1. True Intuition (Tacit Pattern Recognition)
A 20-year analyst recognizes fraud templates, staged personas, and fabricated biographies from micro-signals accumulated over thousands of cases. LLMs have breadth but not depth of case-specific pattern memory. Lexicons and typologies narrow the gap but do not close it.

**Design around:** Human-in-the-loop checkpoints for adverse-media and due-diligence investigations. Red-flag lexicon handles top decile; remainder requires human review.

### F2. Fine-Grained Bayesian Calibration
LLMs produce overconfident posteriors and cannot reliably update probability estimates as evidence accumulates. The Admiralty Code helps but the underlying calibration is unreliable at fine granularity.

**Design around:** Discrete confidence buckets (high/medium/low/uncertain) with strict evidence rules instead of numeric posteriors. Human analyst reviews any high-confidence finding from fewer than 2 primary sources.

### F3. Operational Tradecraft and Attribution Risk
The brain cannot model an adversary's surveillance posture — whether querying a specific source would alert the subject, whether a specific IP pattern indicates monitoring, whether a tripwire URL is being watched.

**Design around:** Hard rules tagging each tool with `attribution_risk`. High-risk tool use requires explicit human opt-in. Brain defaults to passive sources and surfaces high-risk options as escalation items.

### F4. Tacit Cultural Fluency
Reading PH political economy, clan dynamics, religious-social structures, and regional cultural signals requires lived context that cannot be fully encoded in a knowledge file.

**Design around:** Human review checkpoint for investigations with significant political-economy signals. Knowledge files (`ph_political_economy.md`) handle factual layer; interpretive layer requires human analyst.

### F5. Legal and Evidentiary Judgment
Chain of custody, PH Data Privacy Act compliance, admissibility rules, and purpose-limitation law require legal training and cannot be reliably encoded.

**Design around:** `legal_class` tagging on all findings. Final admissibility review is a mandatory human checkpoint before any investigative product is used for legal or regulatory purposes.

---

<a name="hybrid-architecture"></a>
## 8. The Hybrid Human-AI Architecture

### Division of Labor

| Task | Brain | Human |
|------|-------|-------|
| Rapid collection across many sources | ✓ | |
| Pattern matching at scale | ✓ | |
| Structured SAT execution | ✓ (when bound) | |
| Graph building, SNA metrics | ✓ | |
| Admiralty scoring (mechanical) | ✓ | |
| Report assembly | ✓ | |
| PIR definition | | ✓ |
| D&D final assessment | | ✓ |
| Attribution risk decision | | ✓ |
| Cultural/clan context injection | | ✓ |
| SNA interpretation | ✓ (metrics) | ✓ (meaning) |
| Legal/admissibility judgment | | ✓ |
| Audience calibration | ✓ (structural) | ✓ (judgment) |
| Strategic patience (when to stop) | | ✓ |
| Conflicting-signal arbitration | escalate | ✓ |
| Tacit anomaly detection | partial | ✓ |

### Escalation Types

The brain emits structured escalation events when it reaches the boundary of its competence:

```json
{
  "escalation": {
    "type": "human_judgment_required",
    "category": "d_and_d_risk | attribution_risk | conflicting_signals | 
                 legal_class_review | cultural_context | prior_collapse | 
                 sna_interpretation | strategic_patience",
    "context": "...",
    "brain_assessment": "...",
    "question_for_analyst": "...",
    "blocking": true,
    "alternatives_if_no_analyst": ["..."]
  }
}
```

`blocking: true` → brain pauses and waits for human input before continuing.
`blocking: false` → brain continues but flags for async human review.

### UI Components Required

1. **PIR Definition interface** — Structured pre-investigation form. Defines completion criteria and minimum evidence thresholds. Becomes investigation contract.

2. **Human Review Queue** — Panel showing escalations awaiting judgment, sorted by blocking status. Human annotates → feeds back into brain's running context.

3. **Analyst Workspace** — Layer on findings panel. Human can: add context, override confidence with justification, mark findings inadmissible, annotate graph nodes, set branches as do-not-pursue.

4. **SNA Visualization** — Graph rendered with centrality metrics. Human interprets node roles; interpretation becomes a `source_class: human_analyst` finding.

5. **D&D Assessment form** — Brain auto-populates observable indicators (domain ages, content reuse, SEO anomaly scores); human completes the motive/means/opportunity assessment.

6. **Strategic Patience Controls** — "Pause investigation" with scheduled resume. Brain picks up from exact state when human triggers continuation.

### Feedback Loop

Human decisions persist and train the system:
- PIR patterns → pre-populated templates over time
- Escalation resolutions → train escalation classifier (fewer false alarms over time)
- Analyst annotations → accumulate into PH knowledge base
- D&D overrides → feed `investigation_strategy_overlays` alongside grade feedback
- SNA interpretations → annotated graph patterns the brain learns to flag
- Legal class reviews → per-tool `permitted_purposes` refinement

---

<a name="ph-specific"></a>
## 9. Philippine-Specific Intelligence Considerations

These are additional gaps specific to PH investigations beyond the general gap registry.

| Gap | Priority | Implementation Direction |
|-----|----------|--------------------------|
| P1. BIR vs SEC vs DTI registry decision tree | High | Entity class → authoritative registry mapping |
| P2. Barangay-level granularity not required | High | COMELEC + voter records for PH residency claims |
| P3. PRC license number structure unparsed | Medium | Parser + corroboration with credential claims |
| P4. Spanish-era property/family records | Low | For older subjects; parish records and Spanish surname patterns |
| P5. OFW status as dominant prior | High | `migration_corridor_lookup` mandatory when PH residency yields nothing |
| P6. PH political dynasty proximity | Medium | Dynasty reference file; surname × locality × era cross-check |
| P7. 2019 Revised Corporation Code temporal segmentation | Medium | Corporate disclosure rules changed materially in 2019 |
| P8. Tagalog/Filipino legal terminology in court records | Medium | Stemmer/glossary for Tagalog legal terms |
| P9. Chinese-Filipino multi-name aliases | High | Part of `name_variants_ph()` node |
| P10. Regional naming (Cebuano, Ilonggo) | Medium | Regional variant emission for province-tagged investigations |

---

<a name="priorities"></a>
## 10. Implementation Priorities

### Tier 1 — Highest impact, infrastructure exists (do first)

1. **Grounding pass** — Wire `fused_retrieve()` before every brain launch. A-graded priors injected as assertions the brain must affirm or refute. Fixes the single biggest failure: past research ignored.

2. **Conflict detection gate** — Haiku call before research: "do all signals fit one property?" If no → mandatory clarification before any research. Fixes composite-ad and managed-content failures.

3. **Bind existing fusion artifacts** — `ach.py`, `deception.py`, `decay.py`, `pyramid_scoring.py`, `pir.py` are all offline. Make them mandatory constraints validated against brain output. The most leveraged single change.

4. **Source class policy + 2-primary rule** — Tag every finding with `source_class`. Prohibit `training_knowledge` as primary source for `temporal_sensitivity: high` queries. Require ≥2 independent primaries for confidence ≥ 80%.

5. **BROADEN phase** — Mandatory minimum 3 live tool calls before any hypothesis commitment. Training data can name candidates; live sources must confirm them.

6. **PH naming variants** — `name_variants_ph()` node mandatory for PH person investigations. Recall is being silently destroyed.

### Tier 2 — High impact, moderate build cost

7. KAC at PLAN and mid-research stages
8. Falsifier pre-commitment in PLAN output
9. Replan trigger on prior collapse
10. Block-reason taxonomy with evidentiary inference
11. Counter-curation branch mandatory for person investigations
12. Negative-space checks for primary-self claims
13. Entity lineage + Wayback diff mandatory for PH SEC entities
14. PIR definition interface (UI)
15. Human Review Queue (UI)
16. 3-state outcomes in delivery schema

### Tier 3 — Useful, lower leverage

17. Red-flag lexicon
18. SNA metrics computation post-graph-build
19. Event-velocity anomaly detection
20. Audience-specific report generation
21. Estimative language enforcement (ICD 203)
22. Tool-cost reasoning (cheapest-first ordering)
23. Tool improvisation before suggest_plugin
24. Case journal persistence

### Fundamental gaps — Design around

- Human Review Queue handles: D&D final assessment, attribution risk decisions, cultural/clan interpretation, legal/admissibility review, strategic patience, SNA interpretation
- PIR Definition form handles: completion criteria, minimum evidence thresholds

---

<a name="references"></a>
## 11. References and Further Research

### Foundational texts (to review for methodology updates)

- **Richards Heuer** — *Psychology of Intelligence Analysis* (CIA, 1999). ACH methodology. Available free: https://www.cia.gov/static/9a5f1162fd0932c29bfed1c030edf4ae/Pyschology-of-Intelligence-Analysis.pdf
- **ODNI** — *Structured Analytic Techniques for Intelligence Analysis* (3rd ed., 2021). Full SAT catalog. [Requires ODNI access or published summary]
- **Sherman Kent** — *Strategic Intelligence for American World Policy* (1949). Estimative language standards.
- **ICD 203** — *Analytic Standards* (ODNI, 2015). The binding standard for US intelligence community analytic products.
- **Robert Clark** — *Intelligence Analysis: A Target-Centric Approach* (6th ed., 2019). Target system modeling methodology.
- **Bellingcat** — *Bellingcat Methodology Handbook* (2022). OSINT tradecraft applicable to open-source investigations. https://www.bellingcat.com/resources/

### For future research updates

- Review latest ODNI SAT publications for any new techniques added since 2021
- Review Bellingcat published case studies for updated OSINT methodology
- Review academic literature on LLM calibration and uncertainty quantification (for addressing F2)
- Review PH academic and legal literature for updates to corporate registry law and DPA enforcement
- Review emerging AI-human teaming models in intelligence literature (RAND, CNAS publications)

### Areas where this document should be updated

- When new SAT techniques are published by ODNI or CIA
- When LLM capabilities advance meaningfully (particularly in calibration, which may close F2)
- After each significant IS brain failure post-mortem — add to Section 2
- When PH regulatory or legal context changes significantly
- After implementation of Tier 1 priorities — reassess which gaps remain

---

<a name="changelog"></a>
## 12. Changelog

| Date | Version | Changes |
|------|---------|---------|
| 2026-05-10 | 1.0 | Initial document. Based on case analysis of runs 65dc9e39 and 1392fde1, Dyson/Wan Young failure, and systematic gap audit via Claude Opus brainstorm session. |

---

*This document is a living research artifact. It reflects the state of understanding as of its version date. Technology capabilities, intelligence tradecraft, and PH-specific context will evolve — schedule regular reviews.*
