# Universal Research Engine — Design Spec

**Date:** 2026-05-07
**Status:** Draft
**Companion to:** `2026-05-07-comprehensive-investigation-strategy-design.md` (Retrieval category)
**Reference:** `2026-05-07-research-paradigms-reference.md` (full paradigm catalog + decision rationale)

## Problem Statement

The investigative strategy spec covers Retrieval (finding facts about existing entities). But real-world research tasks span 5 epistemic categories: Retrieval, Generation, Prediction, Explanation, and Synthesis. The system needs strategy modules for all 5, plus cross-category transitions for tasks that span multiple categories.

## Architecture Extension

The investigative spec's architecture (selector-centric engine + strategy modules + fusion layer + classification + self-learning) is **universal infrastructure**. This spec adds:

1. **Strategy modules** for Generation, Prediction, Explanation, and Synthesis
2. **Category-specific selector types and pivot patterns** for each
3. **Cross-category transition protocol** for tasks that span multiple categories
4. **Research orchestrator** that detects which category (or sequence of categories) a task requires

### System Architecture (Extended)

```
User Query
    ↓
Research Orchestrator (NEW)
    ├── Classify query into category/categories
    ├── Determine category sequence for multi-category tasks
    └── Load appropriate strategy modules
    ↓
┌─────────────────────────────────────────┐
│ UNIVERSAL ENGINE (from investigative spec)│
│ ├── Selector-centric graph traversal     │
│ ├── Intelligence Fusion Layer            │
│ ├── Classification (Admiralty + STIX)    │
│ └── Self-learning (seed + overlays)      │
└─────────────────────────────────────────┘
    ↓
Category-Specific Strategy Module
    ├── Selector types for this category
    ├── Pivot patterns for this category
    ├── Completeness criteria
    └── Classification depth
    ↓
Output (varies by category)
    ├── Retrieval → Intelligence report
    ├── Generation → Candidate solutions
    ├── Prediction → Scenarios / forecasts
    ├── Explanation → Causal model / root cause
    └── Synthesis → Integrated evidence assessment
```

---

## Part 1: Research Orchestrator

### 1.1 Query Classification

The orchestrator analyzes the research_goal to determine which category or sequence of categories applies.

**Classification signals:**

| Signal in Query | Category |
|----------------|----------|
| "Find", "Investigate", "Profile", "Background check" | Retrieval |
| "Build", "Create", "Design", "Invent", "Develop" | Generation |
| "Predict", "Forecast", "What will", "Trend", "Future" | Prediction |
| "Why", "Root cause", "Diagnose", "How does", "Explain" | Explanation |
| "Review", "Summarize", "Compare", "Evaluate", "Assess" | Synthesis |

**Multi-category detection:**

| Compound Query | Category Sequence |
|---------------|------------------|
| "Build a cure for cancer" | Synthesis → Explanation → Generation → Prediction |
| "Build a better search engine" | Retrieval → Explanation → Generation |
| "Should we acquire Company X?" | Retrieval → Explanation → Synthesis |
| "Why is our system slow and how to fix it?" | Explanation → Generation |
| "What's the state of AI in healthcare and where is it going?" | Synthesis → Prediction |

### 1.2 Category Transition Protocol

When a task spans multiple categories, the orchestrator manages transitions:

```
Category A completes
    ↓
Transition Gate:
    1. Summarize Category A outputs
    2. Extract selectors relevant to Category B
    3. Transform selector types (e.g., "finding" from Retrieval
       becomes "prior_art" in Generation)
    4. Load Category B strategy module
    5. Inject Category A summary as context
    ↓
Category B begins with transformed selectors + context
```

**Selector type transformations across categories:**

| From (Category A) | To (Category B) | Transformation |
|-------------------|-----------------|----------------|
| `finding` (Retrieval) | `prior_art` (Generation) | Existing solution becomes baseline to improve on |
| `finding` (Retrieval) | `evidence` (Synthesis) | Raw finding becomes evidence to weigh |
| `entity` (Retrieval) | `variable` (Explanation) | An entity becomes a factor in causal analysis |
| `gap` (Synthesis) | `problem_statement` (Generation) | An identified gap becomes a problem to solve |
| `root_cause` (Explanation) | `constraint` (Generation) | Understanding why → constraint for design |
| `candidate_solution` (Generation) | `hypothesis` (Explanation) | Proposed solution → testable hypothesis |
| `forecast` (Prediction) | `constraint` (Generation) | Future state → design constraint |

### 1.3 Implementation

**New file:** `app/pipeline/strategies/orchestrator.py`

The orchestrator is a lightweight LLM call that:
1. Receives the research_goal
2. Classifies into category/categories
3. Determines sequence
4. Returns a plan: `[{category, strategy_module, selector_seed, context}]`

This runs BEFORE the main IS brain loop, using a fast/cheap model (Haiku-class).

---

## Part 2: Generation Strategies — "What could exist?"

### 2.1 Generation Selector Types

| Selector Type | Description | Example |
|--------------|-------------|---------|
| `problem_statement` | The problem to solve | "Drug resistance in triple-negative breast cancer" |
| `concept` | A technique, approach, or idea | "CRISPR-Cas9", "transformer architecture" |
| `technique` | A specific method/process | "Reinforcement learning from human feedback" |
| `prior_art` | Existing solution/product/paper | "Keytruda (pembrolizumab)", "GPT-4 architecture" |
| `researcher_lab` | Who's working on this | "Jennifer Doudna / IGI", "DeepMind" |
| `constraint` | Hard boundary on solutions | "Must be oral delivery", "Latency < 100ms" |
| `gap` | What doesn't exist or doesn't work | "No existing solution handles X" |
| `contradiction` | TRIZ: improving X worsens Y | "Increasing strength reduces flexibility" |
| `component` | Part of a system to transform | "The authentication layer", "The drug delivery mechanism" |
| `function` | What the solution must DO | "Manage heat", "Authenticate users", "Kill tumor cells" |
| `dataset_benchmark` | Data available for the problem | "ImageNet", "TCGA genomic data" |

### 2.2 Generation Pivot Patterns

#### Pivot: `problem_statement` →

| Tool | Extracts | New Selectors |
|------|----------|---------------|
| web_search (academic: "survey" + "review") | State of the art | concepts, techniques, gaps, prior_art |
| web_search (industry: products + competitors) | Commercial solutions | prior_art, constraints |
| web_search ("limitations" + "challenges") | Known weaknesses | gaps, constraints |
| run_document_search (patents) | Patent landscape | prior_art, constraints, gaps |
| Google Scholar ("problem statement") | Foundational papers | researchers, techniques, datasets |

#### Pivot: `concept` →

| Tool | Extracts | New Selectors |
|------|----------|---------------|
| web_search (concept + "survey" OR "review") | SOTA review | techniques, gaps |
| web_search (concept + "limitation" OR "fails") | Known weaknesses | gaps |
| web_search (concept + "alternative" OR "vs") | Competing approaches | other concepts |
| web_search (concept + "combined with" OR "integrated") | Combination approaches | concept pairs |
| run_document_search (patent: concept in claims) | Patent coverage | constraints (FTO), prior_art |

#### Pivot: `gap` → **THE CREATIVE PIVOT**

| Tool | Extracts | New Selectors |
|------|----------|---------------|
| web_search (gap description) | Who's working on this? | researchers, nascent techniques |
| web_search (functional abstraction of gap + unrelated field) | **Cross-domain transfer candidates** | concepts from other fields |
| TRIZ contradiction analysis | Which principles resolve this? | inventive principles → candidate solutions |
| Biomimicry search (function: "how does nature [gap]?") | Biological strategies | nature-inspired concepts |

#### Pivot: `contradiction` → (TRIZ)

| Tool | Extracts | New Selectors |
|------|----------|---------------|
| TRIZ matrix lookup (improving × worsening parameter) | Recommended principles (1-4) | inventive principles |
| web_search (principle + domain) | Examples of principle applied | prior_art in other domains |
| SIT operators (subtract/multiply/divide/unify/depend) | Closed-world transformations | candidate_solutions |

#### Pivot: `prior_art` →

| Tool | Extracts | New Selectors |
|------|----------|---------------|
| Citation graph (who cites this?) | Follow-up work, extensions | newer prior_art, gaps addressed |
| Citation graph (what does this cite?) | Foundations, dependencies | foundational concepts |
| Author search (other work by same team) | Related techniques | techniques, datasets |
| web_search (prior_art + "improved" OR "extended") | Improvements | techniques, concepts |

### 2.3 Generation Completeness Checklist

| Dimension | Question | Assessment |
|-----------|----------|-----------|
| State of Art | Do I understand what exists today? | Major approaches mapped with strengths/weaknesses |
| Gap Identification | What doesn't work / doesn't exist? | At least 1 clearly articulated gap |
| Solution Space | Have I explored adjacent fields? | 2+ adjacent domains checked for transferable techniques |
| Feasibility | Can this actually be built? | Constraints identified, no showstoppers |
| Novelty | Is this actually new? | Prior art search confirms no existing solution |
| Competitive Landscape | Who else is trying? | Key researchers/companies mapped |

### 2.4 Generation Classification

Lighter than Retrieval. Key dimensions:

| Dimension | Scale | Purpose |
|-----------|-------|---------|
| Source reliability | Admiralty A-F (same as Retrieval) | How trustworthy is this source? |
| **Maturity** | Theoretical → Experimental → Validated → Production | How proven is this concept? |
| **Reproducibility** | Reproduced / Not reproduced / Not tested | Has the result been independently confirmed? |
| **Applicability** | Direct / Analogous / Speculative | How transferable to our problem? |
| Recency | Current SOTA / Recent / Dated / Superseded | Is this still state-of-the-art? |

### 2.5 Generation Sub-Strategies

#### `strategies/product_innovation.py`

**Use case:** Building a new product or system.
- Priority selectors: problem_statement, concept, prior_art, constraint, gap
- Key pivots: gap → cross-domain transfer, prior_art → citation graph
- Completeness: SOTA + gap + feasibility + novelty + competitive landscape
- Unique: Includes Design Thinking empathy phase if user context is available

#### `strategies/scientific_discovery.py`

**Use case:** Discovering new knowledge / developing hypotheses.
- Priority selectors: problem_statement, concept, technique, dataset, researcher_lab
- Key pivots: concept → limitations → gaps → hypothesis generation
- Completeness: Literature coverage + gap identification + hypothesis formulation + experimental design suggestion
- Unique: Includes hypothesis quality assessment (falsifiable, specific, novel)

#### `strategies/engineering_rd.py`

**Use case:** Maturing a technology through TRL stages.
- Priority selectors: concept, technique, constraint, prior_art, dataset_benchmark
- Key pivots: technique → benchmark results, constraint → feasibility analysis
- Completeness: TRL-appropriate — different at each stage (TRL 1-3: concept validated, TRL 4-6: lab demonstrated, TRL 7-9: operationally proven)
- Unique: TRL assessment of current state + what's needed for next TRL

---

## Part 3: Prediction Strategies — "What will happen?"

### 3.1 Prediction Selector Types

| Selector Type | Description | Example |
|--------------|-------------|---------|
| `signal` | An observed indicator of change | "5 AI startups raised $100M+ this quarter" |
| `trend` | A pattern over time | "Enterprise AI adoption growing 40% YoY" |
| `driver` | A force causing change | "GPU costs declining exponentially" |
| `uncertainty` | A factor that could go either way | "Regulation of AI: strict vs. permissive" |
| `scenario` | A coherent narrative of a possible future | "AI commoditizes in 3 years" |
| `weak_signal` | An early, ambiguous indicator | "3 papers this month on protein folding + drug delivery" |
| `actor` | Entity whose decisions shape the future | "OpenAI", "EU Commission", "NVIDIA" |
| `constraint` | Hard boundary on what's possible | "Physics limits chip density by 2030" |

### 3.2 Prediction Pivot Patterns

#### Pivot: `signal` →

| Tool | Extracts | New Selectors |
|------|----------|---------------|
| web_search (signal + "trend" OR "pattern") | Is this signal part of a trend? | trends |
| web_search (signal + "cause" OR "driver") | What's driving this signal? | drivers |
| web_search (similar signals in adjacent fields) | Is this happening elsewhere? | weak_signals, trends |
| run_google_news (signal keywords, time-filtered) | Signal strengthening or weakening? | (temporal assessment) |

#### Pivot: `trend` →

| Tool | Extracts | New Selectors |
|------|----------|---------------|
| web_search (trend + "projection" OR "forecast") | Expert forecasts | scenarios |
| web_search (trend + "risk" OR "disruption") | What could break this trend? | uncertainties |
| web_search (trend + "driver" OR "caused by") | Underlying forces | drivers |
| web_search (trend + "implication" OR "consequence") | Second-order effects | new trends, signals |

#### Pivot: `uncertainty` →

| Tool | Extracts | New Selectors |
|------|----------|---------------|
| Scenario construction (uncertainty × outcome) | Possible futures | scenarios |
| web_search (uncertainty + "expert opinion") | Expert positions | actor stances |
| web_search (historical precedent of similar uncertainty) | How did this play out before? | prior_art (historical analog) |

### 3.3 Prediction Completeness Checklist

| Dimension | Question | Assessment |
|-----------|----------|-----------|
| Signal Coverage | Have I scanned all relevant signal sources? | News, patents, funding, job postings, academic pubs checked |
| Trend Identification | Are the major trends mapped? | 3+ major trends identified with trajectory |
| Driver Analysis | Do I understand what's driving the trends? | Key drivers identified and assessed for durability |
| Uncertainty Mapping | Have I identified the key unknowns? | 2+ critical uncertainties identified |
| Scenario Construction | Have I built divergent scenarios? | At least 2 scenarios spanning the uncertainty space |
| Actor Assessment | Do I know who shapes this future? | Key decision-makers and their likely moves mapped |

### 3.4 Prediction Classification

| Dimension | Scale | Purpose |
|-----------|-------|---------|
| **Probability** | Kent's WEP (Almost Certain → Almost Certainly Not) | How likely is this outcome? |
| **Confidence** | High / Moderate / Low | How good is the evidence? |
| **Time horizon** | Near (0-1yr) / Medium (1-3yr) / Long (3-10yr) / Speculative (10yr+) | When might this happen? |
| **Impact** | Marginal / Significant / Transformative / Existential | How big is the effect? |
| Signal strength | Strong / Moderate / Weak / Ambiguous | How clear is the indicator? |

### 3.5 Prediction Sub-Strategies

#### `strategies/technology_forecast.py`

- Priority selectors: signal, trend, driver, weak_signal
- Key pivots: weak_signal → trend validation, trend → driver analysis
- Completeness: S-curve position assessed, key uncertainties mapped, 2+ scenarios
- Unique: Technology Radar output (Adopt/Trial/Assess/Hold classification)

#### `strategies/market_forecast.py`

- Priority selectors: trend, driver, actor, constraint
- Key pivots: trend → market sizing, actor → competitive moves
- Completeness: TAM/SAM/SOM estimated, growth trajectory modeled, competitive dynamics mapped

---

## Part 4: Explanation Strategies — "Why does this happen?"

### 4.1 Explanation Selector Types

| Selector Type | Description | Example |
|--------------|-------------|---------|
| `symptom` | An observed problem or anomaly | "Response times increased 3x this week" |
| `hypothesis` | A proposed explanation | "Database index corruption" |
| `variable` | A factor that might be involved | "Server load", "Cache hit rate" |
| `cause` | A confirmed contributing factor | "Missing index on users table" |
| `root_cause` | The fundamental underlying reason | "Schema migration skipped index creation" |
| `feedback_loop` | A self-reinforcing or balancing dynamic | "More users → more load → slower responses → fewer users" |
| `leverage_point` | Where intervention would have most effect | "Add index" vs. "Redesign schema" vs. "Change architecture" |
| `evidence` | Data supporting/contradicting a hypothesis | "Query plan shows sequential scan" |

### 4.2 Explanation Pivot Patterns

#### Pivot: `symptom` →

| Tool | Extracts | New Selectors |
|------|----------|---------------|
| "5 Whys" reasoning | Candidate causes | hypotheses |
| web_search (symptom description) | Known causes of this symptom | hypotheses, prior_art (known fixes) |
| fishbone decomposition (6M categories) | Structured hypothesis space | variables across Man/Machine/Material/Method/Measurement/Environment |

#### Pivot: `hypothesis` →

| Tool | Extracts | New Selectors |
|------|----------|---------------|
| Evidence search (what data would confirm/deny?) | Supporting or contradicting data | evidence |
| Alternative hypothesis generation | Competing explanations | other hypotheses |
| web_search (hypothesis + "cause" OR "because") | Is this a known pattern? | prior_art, root_cause |

#### Pivot: `cause` →

| Tool | Extracts | New Selectors |
|------|----------|---------------|
| "Why?" (next level deeper) | Deeper cause | cause (recursive) or root_cause |
| Systems mapping (what feeds into this?) | Feedback loops | feedback_loops, variables |
| Leverage point analysis (Meadows' 12 levels) | Where to intervene | leverage_points |

### 4.3 Explanation Completeness Checklist

| Dimension | Question | Assessment |
|-----------|----------|-----------|
| Symptom Documentation | Is the problem clearly described with data? | Symptom quantified with metrics/examples |
| Hypothesis Coverage | Have I considered all plausible explanations? | 3+ hypotheses generated across categories |
| Evidence Collection | Is there data to evaluate each hypothesis? | Each hypothesis has supporting and/or contradicting evidence |
| Alternative Elimination | Have alternatives been ruled out? | Hypotheses eliminated with evidence, not assumption |
| Root Cause Depth | Have I gone deep enough? | "5 Whys" reaches a systemic/structural cause |
| Intervention Design | Is the fix addressing the root cause? | Proposed solution targets root, not symptom |

### 4.4 Explanation Sub-Strategies

#### `strategies/root_cause_analysis.py`

- Priority selectors: symptom, hypothesis, evidence
- Key pivots: symptom → 5 Whys, hypothesis → evidence search → elimination
- Completeness: Root cause identified + alternatives eliminated + fix targets root cause
- Unique: ACH mode ON by default (competing hypotheses)

#### `strategies/systems_analysis.py`

- Priority selectors: variable, feedback_loop, leverage_point
- Key pivots: variable → what affects it / what it affects → feedback loop identification
- Completeness: Dominant feedback loops mapped, leverage points ranked
- Unique: Produces causal loop diagrams, identifies counterintuitive dynamics

---

## Part 5: Synthesis Strategies — "What does all evidence say?"

### 5.1 Synthesis Selector Types

| Selector Type | Description | Example |
|--------------|-------------|---------|
| `study` | A research paper, report, or dataset | "Smith et al. 2025 — CRISPR efficacy trial" |
| `framework` | An analytical model to apply | "Porter's Five Forces", "GRADE" |
| `criterion` | A dimension to evaluate against | "Efficacy", "Cost", "Time to market" |
| `claim` | An assertion to verify or weigh | "CRISPR cures 80% of cases" |
| `evidence` | Data supporting or contradicting a claim | "Trial showed 72% response rate, n=50" |
| `perspective` | A stakeholder viewpoint | "Clinician view", "Patient view", "Regulator view" |
| `option` | A choice to evaluate | "Option A: CRISPR therapy", "Option B: CAR-T" |

### 5.2 Synthesis Pivot Patterns

#### Pivot: `study` →

| Tool | Extracts | New Selectors |
|------|----------|---------------|
| Citation graph (cited by) | Related studies | other studies |
| Method extraction | How was this done? | frameworks used |
| Result extraction | What did they find? | claims, evidence |
| Quality assessment | How reliable is this? | (classification: evidence grade) |

#### Pivot: `claim` →

| Tool | Extracts | New Selectors |
|------|----------|---------------|
| web_search (claim + "evidence" OR "study") | Supporting/contradicting studies | evidence, studies |
| web_search (claim + "criticism" OR "rebuttal") | Counter-evidence | contradicting evidence |
| Expert search (who has published on this claim?) | Authority assessment | perspectives |

#### Pivot: `framework` →

| Tool | Extracts | New Selectors |
|------|----------|---------------|
| Apply framework to collected data | Framework-specific findings | claims, evidence, criteria |
| web_search (framework + "limitation") | Framework weaknesses | alternative frameworks |
| Cross-framework synthesis | Convergent and divergent findings | synthesized claims |

### 5.3 Synthesis Completeness Checklist

| Dimension | Question | Assessment |
|-----------|----------|-----------|
| Literature Coverage | Have I found all relevant sources? | Systematic search across databases, deduplication done |
| Quality Assessment | Is each source graded for reliability? | GRADE or equivalent applied to all evidence |
| Claim Mapping | Are all key claims identified and evidenced? | Major claims listed with supporting/contradicting evidence |
| Conflict Resolution | Are contradictions addressed? | Conflicting evidence explicitly resolved (not ignored) |
| Multi-Framework | Have I applied multiple analytical lenses? | 2+ frameworks applied, findings compared |
| Gap Identification | What questions remain unanswered? | Gaps explicitly listed with impact assessment |

### 5.4 Synthesis Sub-Strategies

#### `strategies/systematic_review.py`

- Priority selectors: study, claim, evidence
- Key pivots: study → citation graph → related studies, claim → evidence search
- Completeness: PRISMA-like protocol — systematic search, deduplication, quality grading, meta-synthesis
- Unique: Quantitative synthesis where possible (pooled effect sizes)

#### `strategies/strategic_assessment.py`

- Priority selectors: framework, criterion, option, perspective
- Key pivots: framework → data application → findings, multiple frameworks → synthesis
- Completeness: All relevant frameworks applied, all stakeholder perspectives considered
- Unique: Multi-framework synthesis (PESTLE → Five Forces → SWOT → VRIO)

#### `strategies/decision_analysis.py`

- Priority selectors: option, criterion, evidence
- Key pivots: option × criterion → evidence search → scoring
- Completeness: All options evaluated against all criteria with evidence
- Unique: Decision matrix output with weighted scoring

---

## Part 6: Cross-Category Transition Examples

### Example 1: "Build a cure for cancer"

```
Step 1: SYNTHESIS (systematic_review)
  Selectors: problem_statement → studies, claims, evidence
  Output: "Current SOTA is immunotherapy (PD-1 inhibitors). 40% response rate.
          Gap: non-responders lack tumor-specific T cells."
  
  ─── TRANSITION ───
  gap → problem_statement (for Explanation)
  evidence → variables (for Explanation)

Step 2: EXPLANATION (root_cause_analysis)
  Selectors: symptom ("non-response"), hypotheses
  Output: "Root cause: tumor microenvironment suppresses T cell infiltration.
          Key mechanism: TGF-β signaling creates immune exclusion."
  
  ─── TRANSITION ───
  root_cause → constraint (for Generation)
  mechanism → concept (for Generation)

Step 3: GENERATION (scientific_discovery)
  Selectors: constraint ("must overcome TGF-β suppression"),
             concept ("T cell engineering"), gap ("immune exclusion")
  Output: "Candidate: engineered T cells with TGF-β-resistant receptor +
          CRISPR knockout of PD-1. Cross-domain: nanomaterial delivery
          from materials science for tumor penetration."
  
  ─── TRANSITION ───
  candidate_solution → hypothesis (for Explanation/validation)

Step 4: PREDICTION (technology_forecast)
  Selectors: candidate concept, constraints (regulatory, technical)
  Output: "TRL assessment: currently TRL 2 (concept formulated).
          Timeline to TRL 4 (lab validation): 2-3 years.
          Key uncertainty: CAR-T manufacturing scalability."
```

### Example 2: "Build a state-of-the-art OSINT product" (this project)

```
Step 1: RETRIEVAL (competitive_intel)
  Selectors: product concept → competitor names, features, pricing
  Output: "Competitors: Maltego, SpiderFoot, Recorded Future.
          Gap: none have self-learning investigation strategies."

  ─── TRANSITION ───
  gap → problem_statement, competitor features → prior_art

Step 2: EXPLANATION (user_research / systems_analysis)
  Selectors: symptom ("investigations are shallow"), variables
  Output: "Root cause: LLM-driven investigation lacks strategic depth.
          System: no feedback loop from results to strategy refinement."

  ─── TRANSITION ───
  root_cause → constraint, feedback_loop → design requirement

Step 3: GENERATION (product_innovation)
  Selectors: constraints, gaps, prior_art (NSA architecture patterns)
  Output: "Design: selector-centric model + intelligence fusion layer +
          self-learning strategy evolution. Cross-domain: NATO Admiralty
          classification from intelligence → automated OSINT scoring."
```

---

## Part 7: New Files

| File | Purpose |
|------|---------|
| `app/pipeline/strategies/orchestrator.py` | Research orchestrator — category classification + sequencing |
| `app/pipeline/strategies/product_innovation.py` | Generation: build new products/systems |
| `app/pipeline/strategies/scientific_discovery.py` | Generation: scientific hypothesis + discovery |
| `app/pipeline/strategies/engineering_rd.py` | Generation: TRL maturation |
| `app/pipeline/strategies/technology_forecast.py` | Prediction: emerging tech tracking |
| `app/pipeline/strategies/market_forecast.py` | Prediction: market/demand forecasting |
| `app/pipeline/strategies/root_cause_analysis.py` | Explanation: RCA with 5 Whys + fishbone |
| `app/pipeline/strategies/systems_analysis.py` | Explanation: feedback loops + leverage points |
| `app/pipeline/strategies/systematic_review.py` | Synthesis: literature review + meta-analysis |
| `app/pipeline/strategies/strategic_assessment.py` | Synthesis: multi-framework analysis |
| `app/pipeline/strategies/decision_analysis.py` | Synthesis: multi-criteria decision support |

### Modified Files

| File | Change |
|------|--------|
| `app/pipeline/nodes/intelligent_search.py` | Add orchestrator call before main loop |
| `app/pipeline/strategies/__init__.py` | Register all new strategy modules |
| `app/pipeline/strategies/compiler.py` | Support cross-category transitions |

---

## Part 8: Implementation Phases

### Phase 1: Research Orchestrator
- Category classification from research_goal
- Multi-category sequence detection
- Strategy module loading

### Phase 2: Generation Strategies
- product_innovation, scientific_discovery, engineering_rd strategy modules
- Generation-specific selector types and pivot patterns
- TRIZ contradiction matrix integration (if feasible)

### Phase 3: Prediction + Explanation Strategies
- technology_forecast, market_forecast strategy modules
- root_cause_analysis, systems_analysis strategy modules
- Explanation-specific ACH integration

### Phase 4: Synthesis Strategies + Cross-Category Transitions
- systematic_review, strategic_assessment, decision_analysis strategy modules
- Cross-category transition protocol implementation
- Selector type transformation between categories
