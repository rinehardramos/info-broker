"""Media identification strategy module."""

ENTITY_TYPE = "media_identification"

STRATEGY = """
=== MEDIA IDENTIFICATION STRATEGY ===

goal: Identify unknown show/movie/media clip/advertisement from partial descriptions.
execution_model: log_cycle(PIR + hypotheses) → BROADEN(≥1 search/hypothesis) → RANK → RECURSE → DELIVER

--- PIR TEMPLATE ---

PIR: What show, film, or advertisement does the user's description refer to?
MANDATORY: Content type matches user-described medium (show vs. ad vs. film) | Subject or lead matches user's PRIMARY descriptor
SUPPORTING: Franchise or IP connection present | Release year in stated time window | Platform identified
REJECT IF: Multiple MANDATORY criteria fail and no hypothesis scores above 20%

--- HYPOTHESIS TABLE ---

H1 (franchise-literal): A show or film IN the stated franchise/IP universe
  search: "[franchise] new series [year]" | run_tmdb_search("[franchise] [year]")

H2 (actor-career): An actress or actor FROM the franchise appears in a DIFFERENT new project
  search: "[franchise] actress new series [year]" | "[actor name] 2025 project"
  Note: "girl in spiderman" = Zendaya, not Spider-Noir. Search the actress's filmography.

H3 (genre-blind): PRIMARY signal + SUPPORTING signal only — CONTEXT/franchise dropped entirely
  search: "[primary descriptor] [supporting detail] new series [year]"
  Example: "girl shotgun 2025 series" — no spider-man in the query

H_last (advertisement/campaign): The content is NOT a show — it's a brand ad or streaming platform promo
  search: "[franchise or actor] advertisement 2025" | "[actor] [brand] campaign"
  Trigger: PreFlight confirms "YouTube" or "ad"

--- SCORING NOTES ---

Medium-type signal (from PreFlight "YouTube" / "advertisement"):
  - Content confirmed as ad → candidates that are shows receive heavy penalty
  - H_last (advertisement) score boosted when medium=ad confirmed

CONTEXT signal ("spiderman") is often loose — an actress FROM the franchise in a DIFFERENT project
satisfies context as strongly as a show IN the franchise. Do not over-weight CONTEXT.

tools: run_tmdb_search | run_web_search | run_google_news | run_web_crawl
"""
