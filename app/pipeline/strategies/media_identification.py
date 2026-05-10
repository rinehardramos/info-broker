"""Media identification strategy module."""

ENTITY_TYPE = "media_identification"

STRATEGY = """
=== MEDIA IDENTIFICATION STRATEGY ===

This strategy defines how to identify an unknown show, movie, or media clip from
partial descriptions. Follow the execution model, generate multiple hypotheses,
and validate each before reporting candidates.

--- EXECUTION MODEL ---

1. INTERPRET — Parse the query for: content type (show/movie/ad), platform hints,
   character descriptions, scene descriptions, time period, actor references.

2. HYPOTHESIZE — Generate 3+ competing hypotheses for what the user might be
   describing. NEVER commit to one answer without checking alternatives.

3. VERIFY EACH — For each hypothesis, search for confirming AND disconfirming
   evidence. Use ACH (Analysis of Competing Hypotheses) thinking: which candidate
   has the LEAST disconfirming evidence?

4. CROSS-REFERENCE — Check if the described scene/person actually exists in the
   hypothesized content. A show title match is NOT sufficient — verify the
   specific detail (scene, character, actor) is present.

5. REPORT — Present all viable candidates ranked by confidence, NOT just the
   first match.

--- CRITICAL RULE: MULTI-HYPOTHESIS EXPLORATION ---

NEVER assume the first match is correct. The user may be:
- Confusing two different shows
- Describing a scene from an ad, not the actual show
- Referring to an actress BY A PREVIOUS ROLE ("girl in spiderman" = actress who
  was in Spider-Man, now in a different show)
- Misremembering details

For EVERY identification query:
1. Find at least ONE alternative explanation
2. Verify the specific scene/detail described actually exists in your candidate
3. If the user says "girl in X" — check BOTH interpretations:
   - A character IN show X
   - An ACTRESS FROM show X now appearing in something new

--- KEY PIVOT PATTERNS ---

show/movie descriptor →
- run_tmdb_search(query) — search TMDB for matching titles
- run_multi_search("new [genre] series 2025 OR 2026 [platform]") — broad search across engines
- run_google_news("new [genre] series premiere 2026") — recent premieres
- run_multi_search("[platform] new releases 2026 action drama") for each platform
  (Netflix, HBO, Amazon, Hulu, Apple TV+, Disney+)

character/actor description →
- run_tmdb_search(character description) — find matching characters
- run_multi_search("[previous role] actress new series 2026") — find what the actor is doing NOW
- run_multi_search("cast [previous show] where are they now") — track actor careers

scene description →
- run_multi_search("[show name] trailer shotgun scene") — verify the scene exists
- run_multi_search("[show name] advertisement commercial") — check if from an ad, not the show
- run_google_news("[show name] trailer breakdown") — find trailer analyses describing scenes

streaming platform search →
- For each major platform, search: "new [genre] series [platform] 2025 2026"
- Platforms to check: Netflix, HBO Max, Amazon Prime, Hulu, Apple TV+, Disney+,
  Peacock, Paramount+, MGM+

--- INVESTIGATION PRINCIPLES ---

MULTI-HYPOTHESIS MANDATORY
  Generate at least 3 candidate shows/movies before investigating any one deeply.
  Which candidate has the LEAST disconfirming evidence? That is your top pick.

VERIFY THE SPECIFIC DETAIL
  If the user describes "man with shotgun" — find the ACTUAL scene, not just
  confirm the show has violence.
  If the user says "girl in spiderman" — check BOTH interpretations: character in
  Spider-Man show AND actress from Spider-Man franchise now in a new project.

ACTOR CAREER TRACKING
  "Girl in X" or "guy in X" often means "actress/actor who was in X."
  Check the full cast of X, then check what each actor is currently working on.

PLATFORM-AWARE
  Always check which platform the show is on. The user may have seen it on a
  specific streaming service and the platform narrows the search considerably.

ADVERTISEMENT CHECK
  Scenes described by users are sometimes from trailers or ads, not the show
  itself. Always run a parallel search for "[show] commercial" or "[show] ad".

--- COMPLETENESS CHECKLIST ---
1. Multiple hypotheses generated (3+ candidates)
2. Specific scene/detail verified for top candidate
3. Alternative interpretations explored ("girl in X" = character vs. actress)
4. Streaming platform identified
5. Cast cross-referenced if applicable
6. Trailer/advertisement checked for described scene

--- TOOLS TO USE ---
- run_tmdb_search — primary for title/cast/show identification
- run_multi_search — broad web search across multiple engines
- run_google_news — recent entertainment news and premieres
- run_web_crawl — crawl entertainment sites (IMDB, Rotten Tomatoes, streaming platforms)
- run_serper_search — Google results for entertainment queries
"""
