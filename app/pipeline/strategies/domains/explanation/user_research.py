"""User research explanation sub-strategy module."""

CATEGORY = "explanation"
NAME = "user_research"
DISPLAY_NAME = "User Research"
DESCRIPTION = (
    "Explains user behavior, needs, and mental models through systematic analysis "
    "of behavioral signals, attitudinal data, and usage patterns. Produces "
    "evidence-based user insights to inform product and design decisions."
)
SELECTORS = [
    "user_segment",
    "behavior_pattern",
    "mental_model",
    "job_to_be_done",
    "friction_point",
    "motivation",
    "usage_context",
]

STRATEGY = """
=== USER RESEARCH STRATEGY ===

This strategy explains user behavior, needs, and mental models through systematic
analysis of both behavioral data (what users do) and attitudinal data (what users
say and think). It applies Jobs-to-be-Done (JTBD) theory, behavioral analysis, and
mental model mapping to produce evidence-based insights. Observations trump assumptions.
Validate coverage using the completeness checklist before concluding.

--- EXECUTION MODEL ---

A 5-step user research process:

1. USER SEGMENT DEFINITION — Precisely define whose behavior is being explained:
   - Primary user segment: who are the core users and what characterizes them?
   - Behavioral segments: how do different user groups behave differently?
   - Contextual factors: what usage context defines this segment? (role, industry,
     experience level, device, use case frequency)
   - Anti-users: who is explicitly NOT the target user for this research?
   Broad "general public" segments produce unfocused, low-value research.

2. BEHAVIORAL SIGNAL MINING — Extract what users actually do (not just what they say):
   - Product usage analytics: where do users go? What do they skip? Where do they drop off?
   - Support ticket analysis: what issues surface repeatedly? What workarounds are reported?
   - Search query analysis: what do users search for within the product or in relation to it?
   - App store reviews and product review platforms for actual usage behavior descriptions
   - Community forum discussions for naturalistic usage descriptions and workaround reports
   Behavioral data reveals the gap between intended and actual usage.

3. ATTITUDINAL DATA ANALYSIS — Understand user beliefs, motivations, and mental models:
   - Review mining (G2, Capterra, App Store, Play Store): what do users value? What frustrates?
   - Forum and community discussions: how do users conceptualize and discuss the product domain?
   - Social media: twitter/X, LinkedIn, Reddit for authentic user voice
   - Published user surveys: NPS data, CSAT data, user satisfaction research
   - Interview excerpts or reports where publicly available
   Attitudinal data explains WHY users behave as they do.

4. JOBS-TO-BE-DONE ANALYSIS — Map the functional, emotional, and social jobs:
   - Functional job: what task is the user trying to accomplish?
   - Emotional job: how does the user want to feel while doing it? (confident, in control, safe)
   - Social job: how does the user want to be perceived by others?
   - Progress-making context: what situation triggers the use of this product?
   - Success criteria: how does the user define that the job is done?
   Apply the JTBD interview question framework: "When [situation], I want to [motivation],
   so I can [expected outcome]."

5. INSIGHT SYNTHESIS — Convert findings into actionable insights:
   - Cluster behavioral and attitudinal findings by theme
   - Identify the most frequently occurring, most severe, and most surprising patterns
   - For each insight: state it as "We observed [behavior/finding], which tells us [interpretation]"
   - Prioritize insights by: frequency × severity × strategic relevance
   - Identify insights that challenge prior assumptions — these are highest value
   - Document open questions requiring further primary research

--- PRIORITY SELECTORS (User Research) ---

Ordered by insight generation leverage (highest first):

1. friction_point      — where users struggle; directly actionable for product improvement
2. job_to_be_done      — the real job users are hiring the product for; reveals true needs
3. behavior_pattern    — what users actually do; grounded in observation, not assumption
4. mental_model        — how users conceptualize the domain; shapes UI and communication
5. motivation          — why users engage; drives retention and feature prioritization
6. user_segment        — who the research is about; scopes all collection and analysis
7. usage_context       — environment and conditions of use; shapes design requirements

--- KEY PIVOT PATTERNS ---

friction_point:
  - App store reviews: sort by lowest rating; look for repeated issue descriptions
  - ddg_search "site:reddit.com [product] frustrating" OR "[product] annoying" OR
    "[product] broken" OR "[product] workaround"
  - Support forum public posts for frequently asked questions and reported issues
  - G2 / Capterra: "Cons" sections across reviews; tag recurring themes

job_to_be_done:
  - Review "before and after" stories: what was user doing before? What changed after?
  - Switching stories: why did users switch FROM and TO this type of solution?
  - ddg_search "[product category] why people use" OR "[product category] use case"
  - Case studies and customer stories for explicit job articulations

behavior_pattern:
  - Web analytics public disclosures (if product is public SaaS with published metrics)
  - Product changelogs: what features were deprecated? (signal of low adoption)
  - Community activity: which help articles get most views? Most forum threads?
  - ddg_search "[product] usage data" OR "[product] user behavior research"

mental_model:
  - Vocabulary mining: what words do users use to describe the domain?
    (in reviews, forum posts, tweets) — reveals conceptual frames
  - Misconception patterns: where do users get confused? What do they expect that differs?
  - ddg_search "[domain concept] explained" for how users search to understand it

usage_context:
  - Job title and industry analysis from reviewer profiles
  - ddg_search "[product] used for [use case]" for use case discovery
  - Community forum segmentation: which sub-forums or channels exist? (segment signal)

--- COMPLETENESS CHECKLIST ---

Before closing a user research task, confirm coverage in each area:

1. Segment Definition   — user segment precisely defined with behavioral characteristics
2. Behavioral Data      — actual usage behavior documented from observational sources
3. Attitudinal Data     — user beliefs, motivations, and language documented
4. Jobs-to-be-Done      — functional, emotional, and social jobs mapped
5. Friction Points      — top user struggles identified and quantified by frequency
6. Insight Synthesis    — insights stated with observation → interpretation format; prioritized

Mark each area as: CONFIRMED / PARTIAL / NOT FOUND / NOT ATTEMPTED
"""
