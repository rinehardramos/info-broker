# Research Paradigms Reference — Architectural Decision Record

**Date:** 2026-05-07
**Purpose:** Document all research paradigms discovered during the investigation strategy design process, the rationale for the 5-category taxonomy, and architectural decisions for future review.

---

## 1. How We Got Here

### The Triggering Insight

Query 04692dda exposed that the IS brain performs shallow, cursory investigation. Initial design focused on making investigative (person profiling) research deeper. During brainstorming, we discovered three expanding gaps:

1. **Email discovery was shallow** → led to designing comprehensive OSINT techniques
2. **The system needed intelligence-grade classification** → led to NATO Admiralty, STIX, ACH frameworks
3. **The NSA architecture review** → led to selector-centric model and intelligence fusion layer
4. **"What about creative research?"** → led to discovering the system only supports Retrieval, not Generation/Prediction/Explanation/Synthesis

### The Research Process

We conducted deep dives across:
- OSINT frameworks (OSINT Framework, Bellingcat, Bazzell/IntelTechniques, Trace Labs, SANS)
- Nation-state intelligence (CIA/NATO models, NSA leaked architecture: PRISM/XKeyscore/TIDE)
- Intelligence classification (Admiralty System, STIX 2.1, Sherman Kent's WEP, ACH, PIRs)
- Information quality (Wang & Strong 1996, GRADE, legal standards of proof)
- Academic research methodologies (16+ paradigms)
- Creative/innovation methods (TRIZ, Design Thinking, Biomimicry, SIT, etc.)
- Applied research domains (patent search, threat modeling, RCA, genealogy, drug discovery, etc.)

---

## 2. The 5-Category Taxonomy

### Decision: Organize research paradigms by epistemic stance, not by domain

**Why this choice:**
- Domain-based organization (medical research, legal research, market research) creates silos and misses shared patterns
- Method-based organization (qualitative vs. quantitative) is too abstract
- Epistemic stance ("what is your relationship to reality?") captures the fundamental operational difference that determines what selectors, pivots, and completeness criteria look like

**The 5 categories:**

| # | Category | Epistemic Question | Stance |
|---|----------|-------------------|--------|
| 1 | **Retrieval** | What exists? | Observer of present/past |
| 2 | **Generation** | What could exist? | Creator of the new |
| 3 | **Prediction** | What will happen? | Forecaster of the future |
| 4 | **Explanation** | Why does this happen? | Analyst of causation |
| 5 | **Synthesis** | What does all evidence say? | Integrator of knowledge |

### Alternatives Considered

**Domain-based taxonomy** (medical, legal, business, academic, intelligence):
- Rejected because: real-world tasks cross domains constantly; a VC evaluating a biotech startup needs medical + financial + legal research simultaneously
- Also rejected because: the automated system primitives don't align with domains — they align with epistemic operations

**Intelligence cycle-based** (Direction → Collection → Processing → Analysis → Dissemination):
- Rejected because: this is a process model for ONE type of research (Retrieval), not a taxonomy of ALL research types
- However: the intelligence cycle does inform the execution model within each category

**Academic classification** (exploratory, descriptive, explanatory, correlational, experimental):
- Rejected as the sole taxonomy because: it's too focused on academic research and doesn't account for creative/generative paradigms
- However: these map into our categories (exploratory → Retrieval/Explanation, descriptive → Retrieval, explanatory → Explanation, experimental → Explanation/Generation)

### Completeness Argument

We audited for missing epistemic stances:

| Candidate | Assessment | Classification |
|-----------|-----------|---------------|
| Monitoring/Surveillance | Temporal mode (continuous), not a stance | Mode modifier on any category |
| Diagnostics ("What's wrong?") | Converges to Explanation (symptom → cause) | Sub-paradigm of Explanation |
| Decision Research ("Which option?") | Integrates evidence for choice | Sub-paradigm of Synthesis |
| Normative/Ethics ("What should we do?") | Values layer on Synthesis | Sub-paradigm of Synthesis |
| Red Team/Adversarial | Method applicable to any category | Cross-cutting method (like ACH) |
| Curation/Taxonomy | Organizing knowledge | Sub-paradigm of Synthesis |
| Comparative Research | Comparing entities/systems | Method applicable to Retrieval or Explanation |

**Conclusion:** The 5 categories are complete as epistemic stances. Additional paradigms are either sub-paradigms within a category, temporal modes, or cross-cutting methods.

---

## 3. Full Paradigm Catalog

### Category 1: RETRIEVAL — "What exists?"

| Paradigm | Goal | Key Method | Evidence Standard | Distinguishing Feature |
|----------|------|-----------|-------------------|----------------------|
| Intelligence/OSINT | Uncover hidden truth | Intelligence cycle + SATs | Admiralty A-F / 1-6 | Adversarial — info may be deliberately hidden |
| Due Diligence (M&A) | Assess acquisition target | 7-12 parallel workstreams | Documentary + expert validation | Red-flag oriented, financial impact quantification |
| Fact-Checking | Verify specific claims | Line-by-line verification | Primary source or 2 independent secondaries | Adversarial stance toward own material |
| Legal Research | Determine applicable law | Hierarchical source search | Binding precedent in jurisdiction | Authority is hierarchical (constitution > statute > case) |
| Genealogical Research | Establish identity/relationships | Reasonably exhaustive search | GPS (5 formal elements) | Negative evidence; most formal proof standard |
| Descriptive Research | Document "what is" | Surveys, content analysis | Statistical representativeness | No causal claims, pure measurement |
| Historical/Archival | Reconstruct the past | Primary source analysis, dating | Provenance + multiple dating methods | Source criticism; temporal reconstruction |
| Market Research (secondary) | Inform business decisions | Data aggregation, analysis | Actionable for decisions | Decision-oriented, not knowledge-oriented |

### Category 2: GENERATION — "What could exist?"

| Paradigm | Goal | Key Method | Completeness Criterion | Distinguishing Feature |
|----------|------|-----------|----------------------|----------------------|
| TRIZ | Resolve inventive contradictions | 40 principles + contradiction matrix | All suggested principles evaluated | Lookup table for invention; most automatable |
| Design Thinking | Create human-centered solutions | Empathize → Define → Ideate → Prototype → Test | User need saturation | Discovers latent needs through empathy |
| Biomimicry | Find nature-inspired solutions | Function abstraction → biological search | Taxonomic sampling of relevant organisms | Cross-domain transfer from biology |
| SIT | Transform within closed world | 5 operators × N components | Full operator-component matrix | Closed World constraint increases creativity |
| SCAMPER | Modify existing products/processes | 7 operators applied systematically | All operators × all components | Structured modification checklist |
| Morphological Analysis | Explore combinatorial space | Parameter decomposition + cross-consistency | Mathematically defined (all valid combos) | Zwicky box; finite enumerable space |
| Scientific Discovery | Test hypotheses about nature | Hypothesis → experiment → falsification | Survived rigorous falsification attempts | Inherently creative in hypothesis generation |
| Engineering R&D | Mature tech from concept to deployment | TRL 1-9 stage-gate progression | Operational validation at target conditions | Maturity measured on concrete scale |
| Drug Discovery | Safe, effective treatments | SAR optimization + clinical trial pipeline | Regulatory approval (FDA/EMA) | Multi-parameter optimization; 10-15yr timeline |
| Neural Architecture Search | Discover computational methods | Automated search over architecture space | Sufficient sampling of search space | Meta-creative — computation discovering computation |

### Category 3: PREDICTION — "What will happen?"

| Paradigm | Goal | Key Method | Completeness Criterion | Distinguishing Feature |
|----------|------|-----------|----------------------|----------------------|
| Futures/Foresight | Map possible futures | Scenario planning, Delphi, horizon scanning | Multiple divergent scenarios constructed | Cannot be empirically validated (future hasn't happened) |
| Technology Scouting | Track emerging tech | Continuous monitoring + S-curve analysis | Adequate source coverage, ongoing | Most naturally automatable prediction paradigm |
| VC Deal Evaluation | Predict startup success | Multi-dimensional evaluation grid | All evaluation dimensions assessed | Pattern matching under extreme uncertainty |
| Market Research (primary) | Predict demand/preferences | Surveys, conjoint analysis, experiments | Statistical significance | Decision-oriented forecasting |
| Competitive Intelligence | Anticipate competitor moves | PESTLE → Five Forces → SWOT | Multi-framework synthesis | Weak signal detection for strategic early warning |

### Category 4: EXPLANATION — "Why does this happen?"

| Paradigm | Goal | Key Method | Completeness Criterion | Distinguishing Feature |
|----------|------|-----------|----------------------|----------------------|
| Root Cause Analysis | Find actual underlying cause | 5 Whys, fishbone, fault tree | Alternative hypotheses eliminated | Convergent — starts broad, narrows to one cause |
| Systems Thinking | Understand dynamic behavior | Feedback loop mapping, leverage points | Model reproduces reference behavior | Counterintuitive dynamics; Meadows' 12 leverage points |
| Causal/Experimental Research | Establish cause-effect | Controlled experiments, A/B tests | Statistical significance + effect size | Manipulates variables to prove causation |
| Grounded Theory | Build theory from data | Constant comparative method | Theoretical saturation | Theory EMERGES from data (inductive, not deductive) |
| Threat Modeling | Identify what can go wrong | STRIDE + ATT&CK + attack trees | All components × all threat categories | Adversary-centric thinking; kill chain analysis |
| Ethnographic/User Research | Understand human behavior | Contextual inquiry, diary studies | Theoretical saturation (~12-20 participants) | Discovers latent needs invisible to other methods |

### Category 5: SYNTHESIS — "What does all evidence say?"

| Paradigm | Goal | Key Method | Completeness Criterion | Distinguishing Feature |
|----------|------|-----------|----------------------|----------------------|
| Systematic Review | Authoritative evidence synthesis | PRISMA protocol, meta-analysis | All qualifying studies included | Research ABOUT research; no new primary data |
| Evaluation Research | Judge program effectiveness | Formative + summative evaluation | Logic model fully assessed | Explicitly value-laden — makes a JUDGMENT |
| Patent Search/Prior Art | Determine novelty or FTO | Classification + citation + keyword | All relevant CPC codes searched | Claim-level analysis; temporal logic (in-force vs. expired) |
| Competitive Intelligence (synthesis) | Strategic positioning | Multi-framework integration | All frameworks applied and synthesized | The narrative that emerges from framework convergence |
| Decision Analysis | Choose optimal option | MCDA, AHP, decision trees | All options × all criteria | Integrates evidence INTO a decision |

---

## 4. Cross-Category Observations

### Shared Automation Primitives

These operations cut across all 5 categories:

1. **Source classification and credibility scoring** — used in Retrieval (Admiralty), Generation (peer-reviewed vs. preprint), Synthesis (evidence grading)
2. **Exhaustiveness tracking** — genealogy's GPS, patent search coverage, systematic review inclusion criteria, TRIZ matrix coverage
3. **Conflict detection and resolution** — competing findings (Retrieval), competing hypotheses (Explanation), contradictory evidence (Synthesis)
4. **Graph-based reasoning** — entity graphs (Retrieval), causal graphs (Explanation), citation graphs (Synthesis), patent family graphs (Synthesis), attack trees (Explanation)
5. **Staged pipeline with gates** — drug discovery TRL, VC deal funnel, clinical trials, engineering R&D
6. **Provenance/chain of custody** — critical in Retrieval (intelligence), Synthesis (systematic review), Generation (scientific experiments)
7. **Divergent-then-convergent reasoning** — Design Thinking ideation, scenario planning, hypothesis generation

### Key Dimensions That Vary Across Paradigms

| Dimension | Range |
|-----------|-------|
| Evidence standard | Informal → publishable → regulatory-grade → GPS formal |
| Temporal orientation | Historical reconstruction ↔ Present state ↔ Future prediction |
| Convergence pattern | Broad-to-narrow (RCA) / Parallel (M&A DD) / Staged (drug discovery) / Continuous (tech scouting) |
| Output type | Information / Artifact / Decision / Forecast / Theory / Proof |
| Adversarial posture | Open (most research) / Adversarial (intelligence, fact-checking, red team) |
| Automation readiness | Full (TRIZ matrix) → High (OSINT) → Medium (scientific method) → Low (ethnography) |

### Real-World Tasks Cross Categories

| Task | Retrieval | Generation | Prediction | Explanation | Synthesis |
|------|-----------|-----------|-----------|-------------|-----------|
| "Cure cancer" | Systematic review of treatments | Novel drug/therapy design | Clinical trial outcome prediction | Why do current treatments fail? | Meta-analysis of trial data |
| "Build SOTA product" | Competitive intel | Design thinking + engineering | Market/tech forecasting | User research: why do users struggle? | Strategic positioning |
| "Investigate a person" | OSINT profiling | — | Behavioral prediction | Why did they do X? | ACH for conflicting evidence |
| "Should we acquire Company X?" | Due diligence | — | Financial projections | RCA on why metrics declined | Valuation synthesis |
| "Why is our system slow?" | Log/metric retrieval | — | — | RCA + systems thinking | — |
| "What should our 5-year strategy be?" | Competitive intel | Scenario creation | Futures/foresight | Systems dynamics modeling | Multi-framework synthesis |

---

## 5. Architectural Decisions

### Decision 1: Selector-centric model as universal execution engine

**Choice:** All research categories use a selector-centric graph traversal model, with category-specific selector types and pivot patterns.

**Why:** The NSA architecture review showed that selector-centric pivoting is the most scalable pattern for multi-source information fusion. It works because:
- It naturally handles cross-source deduplication (same selector found in multiple sources)
- It enables entity resolution (linking fragments to the same real-world entity)
- It supports recursive investigation (new selectors feed back into the loop)
- It's category-agnostic — "email" is a Retrieval selector, "contradiction" is a Generation selector, "weak signal" is a Prediction selector, "symptom" is an Explanation selector

**Alternative rejected:** Source-centric model (query each source in sequence). Rejected because it produces shallow, disconnected results and doesn't naturally support cross-source corroboration.

**Risk:** The abstraction of "selectors" works well for Retrieval (identifiers are concrete), but may feel forced for Generation (contradictions and functions are more abstract). Monitor whether the selector metaphor holds across all 5 categories in practice.

### Decision 2: Strategy modules as the context-adaptation layer

**Choice:** Each research context (person investigation, lead gen, scientific discovery, etc.) gets its own strategy module that defines selector priorities, pivot patterns, completeness criteria, and classification depth.

**Why:** The core engine (selector extraction, entity resolution, graph traversal, classification) is universal. Only the strategy needs to change per context. This mirrors how intelligence agencies work: the collection infrastructure is shared, but the PIRs (Priority Intelligence Requirements) change per mission.

**Alternative rejected:** Separate engines per research category. Rejected because it would mean duplicating the fusion layer, graph system, and classification framework for each category.

**Risk:** Strategy modules may need to be very long/detailed to adequately guide the IS brain for complex research types. Token overhead in the prompt is a concern. Monitor prompt size vs. investigation quality trade-off.

### Decision 3: Classification as a practical subset with toggleable advanced modes

**Choice:** Default classification is Admiralty source/info scoring + STIX confidence + corroboration tracking + perishability. Advanced modes (ACH, PIR decomposition) are opt-in per strategy module.

**Why:** Full classification (ACH + PIR) adds significant complexity that isn't needed for all research types. Lead generation doesn't need competing hypotheses analysis. But due diligence investigations do. Making advanced modes toggleable keeps the base system simple while enabling depth when needed.

**Alternative rejected:** Full classification always on. Rejected because the overhead would slow down simple tasks and bloat output for use cases that don't need it.

### Decision 4: Self-learning loop with seed + overlay architecture

**Choice:** Static seed strategies (version-controlled files) with database-backed learned overlays (reinforce/prune/discover/upgrade signals).

**Why:** 
- Seeds provide a working baseline before the system has any experience
- Overlays capture what works without modifying the baseline (easy to reset)
- The 4-quadrant tactic classification (high-priority/sentinel/situational/prune) handles the critical edge case of low-yield/high-value tactics
- Confidence decay prevents stale overlays from persisting indefinitely

**Alternative rejected:** Fully dynamic strategies with no seed. Rejected because cold-start would produce random investigation patterns. Also rejected: static-only strategies, because they can't adapt to what works in practice.

### Decision 5: Five research categories, not more

**Choice:** Exactly 5 epistemic categories as the top-level taxonomy.

**Why:** Exhaustive audit found no additional epistemic stance that isn't a sub-paradigm, temporal mode, or cross-cutting method of an existing category. The 5 categories map to fundamental operations: observe/create/forecast/explain/integrate. Adding more would create overlapping categories that confuse the strategy selection system.

**Reviewed and classified as sub-paradigms:** Monitoring (temporal mode), Diagnostics (→ Explanation), Decision Research (→ Synthesis), Normative (→ Synthesis + values), Red Team (→ cross-cutting method), Curation (→ Synthesis), Comparative (→ method).

---

## 6. Future Review Checklist

When reviewing this architecture in the future, validate:

1. **Does the selector metaphor hold?** Check if "selectors" for Generation/Prediction/Explanation categories feel natural or forced to users.
2. **Is prompt overhead manageable?** Measure token count of compiled strategies and their impact on IS brain performance.
3. **Does the 5-category taxonomy cover new paradigms?** If a user requests a research type that doesn't fit, the taxonomy needs revision.
4. **Is the self-learning loop producing useful overlays?** Check that overlays are accumulating, sentinels are being detected, and pruning isn't removing valuable tactics.
5. **Are cross-category transitions working?** Real tasks cross categories. The system should handle "start as Retrieval, shift to Explanation, then Generation" smoothly.
6. **Is classification depth appropriate per context?** Check that lead gen isn't over-classified and due diligence isn't under-classified.
