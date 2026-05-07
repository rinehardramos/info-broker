"""Synthesis research strategy module."""

ENTITY_TYPE = "synthesis"

STRATEGY = """
=== SYNTHESIS RESEARCH STRATEGY ===

This strategy defines how to conduct a rigorous synthesis of existing knowledge
across multiple sources, studies, or perspectives. The goal is to produce an
integrated, balanced, and well-grounded conclusion that reflects the full
evidentiary landscape — not a cherry-picked subset. Follow the execution model,
honor the priority selector order, and validate coverage using the completeness
checklist before concluding.

--- EXECUTION MODEL ---

A 7-step search-to-conclusion process:

1. SYSTEMATIC SEARCH — Define inclusion and exclusion criteria before searching.
   Search multiple independent databases, repositories, and source types. Document
   the search strategy (keywords, filters, date ranges) so it can be reproduced.
   Do not stop when you find confirming sources — search until no new relevant
   sources emerge.

2. QUALITY ASSESSMENT — Grade every source before extracting its claims. Apply
   a consistent quality rubric: study design, sample size, methodology, replication
   status, funding conflicts, and peer review status. Weight higher-quality sources
   more heavily in the synthesis.

3. CLAIM EXTRACTION — Extract specific, falsifiable claims from each source.
   Record the claim, the source, the quality grade, and the evidence type
   (experimental, observational, theoretical, anecdotal). Avoid paraphrasing that
   introduces interpretation.

4. EVIDENCE MAPPING — Map claims across sources. Identify where multiple sources
   agree (convergence), where they disagree (conflict), and where no source has
   addressed a question (gap). Build an evidence matrix.

5. CONFLICT RESOLUTION — For each conflict, investigate the source of disagreement:
   different populations, methodologies, time periods, or definitions? Determine
   whether the conflict is resolvable (e.g., one study is higher quality) or
   reflects genuine uncertainty. Document unresolved conflicts explicitly.

6. MULTI-FRAMEWORK ANALYSIS — Apply at least two analytical frameworks to the
   synthesized evidence. Different frameworks surface different implications.
   Note where frameworks agree and where they diverge in their conclusions.

7. GAP IDENTIFICATION — After synthesis, identify what remains unanswered.
   Document knowledge gaps explicitly: these become the basis for future research
   recommendations or caveats on the conclusions.

--- PRIORITY SELECTORS (Synthesis) ---

Ordered by synthesis leverage (highest priority first):

1. study       — primary source of evidence; must be quality-graded before use
2. framework   — analytical lens used to interpret and organize evidence
3. criterion   — inclusion/exclusion rule or evaluation standard applied to sources
4. claim       — specific, falsifiable assertion extracted from a source
5. evidence    — data, measurements, or observations supporting or contradicting a claim
6. perspective — viewpoint or theoretical stance held by a source or community
7. option      — policy, intervention, or decision alternative being evaluated

--- KEY PIVOT PATTERNS ---

study:
  - citation graph: traverse forward (who cited this?) and backward (what did this cite?)
  - method extraction: identify study design, sample characteristics, controls, and limits
  - result extraction: record effect sizes, confidence intervals, and p-values; not just
    "significant" or "not significant"
  - quality grading: apply GRADE, CONSORT, or domain-appropriate quality rubric
  - find replications: search for studies that attempted to reproduce the findings

claim:
  - supporting evidence search: find independent sources that corroborate this claim
  - contradicting evidence search: find sources that challenge or refute this claim
  - expert search: find domain authorities who have assessed this claim
  - scope check: under what conditions, populations, or contexts does this claim hold?

framework:
  - apply framework to the synthesized data: what conclusions does it produce?
  - find limitations of the framework: when does it break down or mislead?
  - cross-framework synthesis: where multiple frameworks agree, confidence is higher;
    where they diverge, document the divergence as a genuine uncertainty

perspective:
  - identify the community or school of thought holding this perspective
  - find the strongest articulation of this perspective in the literature
  - find the strongest critique of this perspective
  - assess whether the perspective is empirically testable or paradigmatic

option:
  - evidence base: what studies support or oppose this option?
  - trade-off analysis: what does this option optimize for? what does it sacrifice?
  - implementation evidence: has this option been tried? with what results?
  - stakeholder impacts: who benefits and who bears costs under this option?

--- INVESTIGATION PRINCIPLES ---

SYSTEMATIC NOT CHERRY-PICKED
  The search strategy must be defined before the search begins. Do not start with
  a conclusion and search for confirming sources. Every source that meets inclusion
  criteria must be included, regardless of whether it supports the working hypothesis.

GRADE EVERY SOURCE
  Ungraded sources are not equal. A blog post and a randomized controlled trial
  are not equivalent evidence. Apply a consistent quality rubric and weight
  evidence accordingly. Document the grading in the evidence matrix.

RESOLVE CONFLICTS
  Conflicting evidence is not a reason to avoid a conclusion — it is information
  about the limits of current knowledge. Investigate every conflict. Document
  whether it is resolvable or reflects genuine uncertainty. Do not hide conflicts
  by omission.

APPLY MULTIPLE FRAMEWORKS
  A single analytical framework produces a single interpretation. Apply at least
  two frameworks to surface assumptions embedded in each. Cross-framework
  convergence is stronger evidence than single-framework consistency.

IDENTIFY GAPS
  What the synthesis cannot conclude is as important as what it can. Explicit gap
  identification prevents overreach and provides an honest assessment of the
  confidence level attached to each conclusion.

--- COMPLETENESS CHECKLIST ---

Before closing a synthesis research task, confirm coverage in each area:

1. Literature Coverage       — systematic search documented; all qualifying sources
                               included; no cherry-picking
2. Quality Assessment        — every source graded using a consistent rubric;
                               grades recorded in evidence matrix
3. Claim Mapping             — claims extracted, mapped across sources; convergence
                               and conflict zones identified
4. Conflict Resolution       — every conflict investigated; resolved or documented
                               as genuine uncertainty
5. Multi-Framework Analysis  — at least 2 frameworks applied; agreements and
                               divergences documented
6. Gap Identification        — knowledge gaps explicitly listed; caveats on
                               conclusions scope-limited accordingly

Mark each area as: CONFIRMED / PARTIAL / NOT FOUND / NOT ATTEMPTED
"""
