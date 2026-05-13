"""Business Intelligence meta-strategy module."""

NAME = "business_intelligence"
DISPLAY_NAME = "Business Intelligence"
DESCRIPTION = "Competitive and corporate intelligence: job signals, tech stack, patents, financials, supply chain, executive movement."
TRIGGER_SIGNALS = [
    "company", "competitor", "market", "industry", "revenue", "growth",
    "strategy", "product", "funding", "startup", "enterprise", "b2b",
    "SaaS", "technology stack", "hiring", "job posting",
]
ENTITY_TYPES = ["company", "lead", "due_diligence", "market_forecast"]
ALWAYS_ON = False

STRATEGY_TEXT = """
=== BUSINESS INTELLIGENCE META-STRATEGY ===

CI_LIFECYCLE: Requirements -> Collection -> Processing -> Analysis -> Dissemination -> Feedback.
  state requirement type first: strategic (long-horizon) | tactical (specific move) | operational (current pricing/positioning)

JOB_POSTING_SIGNALS [6-12 month lead time]:
  HIGH: multiple postings across departments + exec hire with domain expertise = active initiative
  MEDIUM: staff-level hire in new tech = R&D bet | posting in new geography = market expansion
  queries: run_multi_search("site:greenhouse.io OR site:lever.co OR site:linkedin.com/jobs {company} {role}") | run_glassdoor_reviews

TECH_STACK_INTEL:
  current: site fingerprinting | job postings (future stack — hiring 6 months before deployment) | GitHub (open-source strategy)
  queries: run_multi_search("{company} site:builtwith.com OR site:stackshare.io") | run_shodan_search("org:{company}")

PATENT_INTEL [12-18 month lead time]:
  filing velocity = innovation pace | co-citation networks = capability transfer | inventor mobility = R&D direction
  queries: run_multi_search("site:patents.google.com OR site:lens.org {company} {tech_area}")

FINANCIAL_INTEL:
  public: run_sec_edgar (10-K/10-Q/8-K/DEF 14A); YoY diff of "Risk Factors" + "Competition" = strategic shift
  MD&A hedging spike = upcoming guide-down; earnings Q&A > prepared remarks (less rehearsed)
  private: run_multi_search("site:crunchbase.com OR site:pitchbook.com {company}")

SUPPLY_CHAIN_INTEL: US ocean imports are public record (suppliers, HS codes, volumes, manufacturing locations).
  queries: run_multi_search("site:importyeti.com OR site:panjiva.com {company}") -> recurse into supplier imports for Tier-2

EXECUTIVE_MOVEMENT: C-suite origin > title. Need >=2 correlated moves for signal.
  queries: run_linkedin_profile_search + run_google_news("{exec} joins OR leaves {company}")

WIN_LOSS_INTEL: G2/TrustRadius "cons" field = highest signal (users honest about negatives). Topic-model pain points -> competitor roadmap.

KEY_TOOLS:
  job data: Greenhouse/Lever/Lightcast | web traffic: SimilarWeb/Semrush (trend only)
  funding: Crunchbase/PitchBook | reviews: G2/TrustRadius/Glassdoor (delta/velocity, not absolute)
  ad intel: Meta Ad Library (free), Google Ads Transparency | supply chain: ImportYeti (free), Panjiva | SEC: run_sec_edgar
"""
