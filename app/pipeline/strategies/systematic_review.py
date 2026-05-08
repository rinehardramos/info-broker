"""Systematic review research strategy module."""

ENTITY_TYPE = "systematic_review"

STRATEGY = """
=== SYSTEMATIC REVIEW STRATEGY ===

This strategy guides the conduct of a rigorous systematic review following a
PRISMA-like protocol: exhaustive search, transparent deduplication, quality grading
using the GRADE framework, and meta-synthesis. The output must be reproducible —
the search strategy is documented in full. Validate coverage using the completeness
checklist before concluding.

--- EXECUTION MODEL ---

A 6-step systematic review process:

1. PROTOCOL DEFINITION (PRISMA-like) — Define the review protocol before searching:
   - Research question using PICO/PECO framework:
     * Population: who or what is studied
     * Intervention/Exposure: what is applied or observed
     * Comparator: what it is compared to
     * Outcome: what is measured
   - Eligibility criteria: inclusion and exclusion rules (study design, date range,
     language, population characteristics, outcome measures)
   - Search databases: PubMed, Embase, Web of Science, Scopus, Cochrane, grey literature
   - Outcome measures: primary and secondary outcomes to be extracted
   Register the protocol (OSF, PROSPERO) if conducting for publication.

2. EXHAUSTIVE SEARCH — Execute the search across all specified databases:
   - Construct database-specific search strings using MeSH terms and free text
   - Apply identical logical structure across all databases (AND/OR operators)
   - Search grey literature: government reports, conference proceedings, theses,
     clinical trial registries (ClinicalTrials.gov), preprint servers
   - Contact domain experts for unpublished studies or data
   - Document: databases searched, date of search, total records retrieved per source

3. SCREENING AND DEDUPLICATION — Process retrieved records systematically:
   - Deduplicate: remove duplicate records across databases (Zotero, Rayyan, Covidence)
   - Title/abstract screening: apply inclusion/exclusion criteria independently;
     dual-reviewer process recommended; resolve disagreements by consensus or third reviewer
   - Full-text screening: apply eligibility criteria to full text; document exclusion
     reasons for each excluded study
   - Produce PRISMA flow diagram: records identified → deduplicated → screened →
     assessed → included

4. DATA EXTRACTION — Extract data from all included studies using a standardized form:
   - Study characteristics: design, population, sample size, setting, date
   - Intervention/exposure details
   - Outcome data: effect sizes, confidence intervals, p-values, follow-up duration
   - Risk of bias assessment per study (Cochrane RoB 2, Newcastle-Ottawa, ROBINS-I
     as appropriate to study design)
   Dual extraction with reconciliation is the gold standard.

5. QUALITY GRADING (GRADE Framework) — Assess the certainty of evidence for each outcome:
   - Start at High certainty (RCT evidence) or Low certainty (observational evidence)
   - Downgrade for: risk of bias, inconsistency, indirectness, imprecision, publication bias
   - Upgrade for: large effect size, dose-response, all plausible confounding increases effect
   - Assign final certainty: High / Moderate / Low / Very Low
   - Document rating rationale for every outcome assessed

6. META-SYNTHESIS AND CLAIM MAPPING — Synthesize across studies:
   - Quantitative synthesis: meta-analysis if homogeneity allows (I² statistic, forest plot)
   - Qualitative synthesis: thematic synthesis or narrative synthesis if heterogeneous
   - Claim mapping: map each conclusion to the studies supporting it and their GRADE rating
   - Conflict resolution: document contradictions and explain them (population differences,
     methodological variation, publication bias); do not suppress contradictory evidence
   - Gap identification: document what the evidence does not address

--- PRIORITY SELECTORS (Systematic Review) ---

Ordered by research leverage (highest priority first):

1. research_question  — the PICO/PECO-structured question driving the review
2. eligibility        — inclusion/exclusion criteria defining the evidence base
3. search_strategy    — databases, search strings, and grey literature sources
4. study             — individual study characteristics and findings
5. quality_grade     — GRADE certainty rating per outcome
6. claim             — specific factual assertion supported by the evidence base
7. gap               — identified absence in the evidence base

--- KEY PIVOT PATTERNS ---

research_question:
  - PICO framework: structure question before searching (prevents scope creep)
  - PROSPERO registry for existing registered reviews on same question
  - Cochrane Library for existing systematic reviews to avoid duplication

search_strategy:
  - MeSH term lookup (NLM MeSH browser) for PubMed-optimized terms
  - Emtree terms for Embase; CINAHL headings for nursing/allied health
  - Search filter validation: compare known-relevant papers against search results
  - PubMed: use "systematic review" filter to retrieve existing meta-analyses

quality_grade:
  - Cochrane Handbook for Systematic Reviews for RoB 2 tool guidance
  - GRADE handbook (gradeworkinggroup.org) for certainty rating methodology
  - Eppi-Centre for guidance on qualitative evidence synthesis

claim:
  - Forest plot pooled estimate as the primary quantitative claim anchor
  - Sensitivity analysis to test claim robustness to study exclusion decisions
  - Subgroup analysis for heterogeneous effect modifiers

gap:
  - "Future research" sections of included reviews as gap inventory
  - Funnel plot asymmetry for publication bias in small-study effects
  - GRADE "Very Low" ratings flag areas needing primary research

--- INVESTIGATION PRINCIPLES ---

PRISMA PROTOCOL DISCIPLINE
  Define the protocol before searching. Decisions made post-hoc to include or exclude
  studies introduce bias. Pre-registration forces transparency.

EXHAUSTIVE SEARCH
  Incomplete search produces biased reviews. Search all major databases, grey
  literature, and trial registries. Document every source searched and every
  record retrieved.

DEDUPLICATION
  Cross-database searches produce duplicates. Deduplication must be systematic,
  not manual. Missed duplicates inflate sample sizes; double-counting inflates
  confidence.

QUALITY GRADING (GRADE)
  Do not aggregate evidence without grading its certainty. A conclusion based on
  Very Low certainty evidence requires stronger caveats than one based on High
  certainty. GRADE makes this explicit.

META-SYNTHESIS
  Quantitative meta-analysis is only valid when studies are sufficiently homogeneous
  (I² < 50% is a rough threshold, but clinical and methodological heterogeneity
  matter equally). When heterogeneous, use thematic or narrative synthesis.

CONFLICT RESOLUTION
  Contradictory findings must be explained, not suppressed. Investigate the source of
  contradictions (population differences, outcome measurement variation, bias) and
  document the explanation transparently.

--- COMPLETENESS CHECKLIST ---

Before closing a systematic review task, confirm coverage in each area:

1. Search Exhaustive    — all specified databases searched; grey literature searched;
                          search strings and retrieval counts documented
2. Deduplication        — duplicate records removed; PRISMA flow diagram constructed;
                          exclusion reasons documented for all full-text exclusions
3. Quality Grading      — GRADE certainty assessed for each primary outcome; rating
                          rationale documented; risk of bias assessed per study
4. Claim Mapping        — each major conclusion mapped to supporting studies and
                          GRADE certainty rating; evidence strength stated explicitly
5. Conflict Resolution  — contradictory findings identified and explained; sources
                          of heterogeneity documented
6. Gap Identification   — evidence gaps documented; future research priorities stated;
                          PROSPERO/existing review overlap assessed

Mark each area as: CONFIRMED / PARTIAL / NOT FOUND / NOT ATTEMPTED
"""
