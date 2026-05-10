"""Media identification strategy module."""

ENTITY_TYPE = "media_identification"

STRATEGY = """
=== MEDIA IDENTIFICATION STRATEGY ===

goal: Identify unknown show/movie/media clip from partial descriptions. Generate multiple hypotheses, validate each before reporting.
execution_model: interpret → hypothesize(3+) → verify_each(confirm+disconfirm) → cross_reference → report(all viable candidates ranked)

--- CRITICAL RULE: MULTI-HYPOTHESIS EXPLORATION ---

NEVER assume the first match is correct. User may be: confusing two shows | describing an ad scene not the show | referring to actress BY PREVIOUS ROLE ("girl in spiderman" = actress now in new show) | misremembering details.
For EVERY query: find ≥1 alternative explanation | verify specific scene/detail exists in candidate | check BOTH interpretations of "girl in X" (character IN X vs actress FROM X in new project).

pivots:
show/movie descriptor → run_tmdb_search | multi_search("new [genre] series [year] [platform]") | run_google_news
character/actor description → run_tmdb_search(character) | multi_search("[prev role] actress new series [year]")
scene description → multi_search("[show] trailer [scene type]") | multi_search("[show] advertisement commercial")
streaming platform → search per platform: Netflix | HBO Max | Amazon Prime | Hulu | Apple TV+ | Disney+

principles: MULTI-HYPOTHESIS(≥3 candidates) | VERIFY-SPECIFIC-DETAIL | ACTOR-CAREER-TRACKING | ADVERTISEMENT-CHECK

COMPLETENESS CHECKLIST: multiple_hypotheses(3+) | specific_detail_verified | alternative_interpretations_explored | streaming_platform_identified | cast_cross_referenced | trailer_ad_checked

tools: run_tmdb_search | run_multi_search | run_google_news | run_web_crawl | run_serper_search
"""
