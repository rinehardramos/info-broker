"""Design thinking generation sub-strategy module."""

CATEGORY = "generation"
NAME = "design_thinking"
DISPLAY_NAME = "Design Thinking"
DESCRIPTION = (
    "Human-centered innovation framework that moves from deep user empathy through "
    "problem reframing to divergent ideation and rapid prototyping. Produces "
    "validated problem statements and prioritized solution concepts."
)
SELECTORS = [
    "user_persona",
    "pain_point",
    "how_might_we",
    "prototype_concept",
    "user_need",
    "constraint",
    "insight",
]

STRATEGY = """
=== DESIGN THINKING STRATEGY ===

This strategy applies human-centered design methods to generate innovative solutions
to user problems. It follows the five-stage design thinking process: Empathize,
Define, Ideate, Prototype, Test. The process is non-linear — insights from later
stages loop back to earlier ones. Validate coverage using the completeness checklist
before concluding.

--- EXECUTION MODEL ---

A 5-stage design thinking process:

1. EMPATHIZE — Build a deep, evidence-based understanding of the user:
   - Who is the user? Define primary and secondary user personas with specificity.
   - What are they trying to accomplish? Identify jobs-to-be-done.
   - What are their frustrations, workarounds, and unmet needs?
   - Gather empathy data from: user reviews, forum posts, support tickets,
     social media discussions, and interview transcripts if available.
   - Observe the user's environment: what tools and processes do they already use?
   Avoid assumptions — everything must be grounded in user evidence.

2. DEFINE — Synthesize empathy data into a sharp problem statement:
   - Cluster raw observations into themes using affinity mapping
   - Identify the core tension: what does the user need vs. what exists?
   - Formulate a Point of View (POV): "[User] needs [need] because [insight]"
   - Convert the POV into How Might We (HMW) questions that open ideation:
     "How might we make it easier for [user] to [accomplish goal] without [constraint]?"
   - Validate the problem statement: is this a real problem, not an assumed one?

3. IDEATE — Generate a wide range of solution concepts without judgment:
   - Quantity over quality: generate 20+ concepts before filtering
   - Apply ideation techniques: SCAMPER (Substitute, Combine, Adapt, Modify, Put to
     other uses, Eliminate, Reverse), worst possible idea reversal, random stimulus
   - Draw from analogous domains: how has this type of problem been solved elsewhere?
   - Build on weak ideas — "yes, and" rather than "no, but"
   - Defer evaluation until the ideation phase is complete

4. PROTOTYPE CONCEPT — Select the most promising concepts and sketch them:
   - Identify top 3-5 concepts by voting against: user desirability, feasibility,
     and business viability
   - Build a "Frankenstein" concept combining the best elements of top ideas
   - Describe each prototype concept: core user interaction, key functionality,
     value proposition, and distinguishing feature
   - Keep prototypes rough — the goal is learning, not polishing

5. TEST HYPOTHESES — Define how each prototype concept would be validated:
   - What assumption is being tested?
   - What user behavior or feedback would confirm/disconfirm the assumption?
   - Minimum viable experiment: what is the cheapest way to get a signal?
   - Define success criteria before testing begins

--- PRIORITY SELECTORS (Design Thinking) ---

Ordered by process leverage (highest first):

1. user_persona       — who the solution is for; anchors all empathy work
2. pain_point         — the user's frustration; the problem to be solved
3. user_need          — the underlying need (functional, emotional, or social)
4. insight            — the non-obvious truth discovered through empathy research
5. how_might_we       — the generative question that frames ideation
6. constraint         — boundaries (technical, financial, regulatory) that shape solutions
7. prototype_concept  — early-stage solution concept for validation

--- KEY PIVOT PATTERNS ---

user_persona + pain_point:
  - Product review sites (G2, App Store, Play Store, Trustpilot): 2- and 3-star reviews
    reveal what users hate about current solutions — gold for pain point discovery
  - Reddit: ddg_search "site:reddit.com [user type] [problem area] frustrated OR annoyed OR help"
  - Twitter/X: google_news "[user type] [problem]" for real-time frustration signals
  - LinkedIn posts from practitioners describing workflow challenges

insight (from secondary research):
  - ddg_search "[user type] behavior study" OR "[user type] research findings"
  - Academic HCI (Human-Computer Interaction) and UX research publications
  - Nielsen Norman Group reports for UX research findings
  - IDEO.org and design thinking publications for analogous case studies

how_might_we (ideation):
  - ddg_search "how might we [problem area]" for design challenge examples
  - IDEO Design Kit (designkit.org) for methods and case studies
  - Design Thinking for Educators and Stanford d.school resources
  - web_search_fetch design sprint facilitation guides for structured HMW exercises

analogous domain (for ideation):
  - ddg_search "[core problem type] solved [different industry]"
  - TED Talks and conference presentations in adjacent domains
  - Case studies: how did [analogous domain] solve [analogous problem]?

prototype_concept:
  - ddg_search "[concept type] prototype validation method"
  - Product Hunt for competitive solutions in the problem space
  - App store listings for feature benchmarking and positioning gaps

--- COMPLETENESS CHECKLIST ---

Before closing a design thinking research task, confirm coverage in each area:

1. User Empathy        — primary user persona defined with evidence; pain points documented
2. Problem Definition  — Point of View and HMW questions articulated; validated as real
3. Ideation Coverage   — at least 10 distinct solution concepts generated
4. Prototype Concepts  — top 3 concepts selected with value proposition for each
5. Test Hypotheses     — key assumption and validation approach defined per concept
6. Constraints Mapped  — technical, financial, and regulatory constraints documented

Mark each area as: CONFIRMED / PARTIAL / NOT FOUND / NOT ATTEMPTED
"""
