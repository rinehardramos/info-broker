# Lessons Learned & Optimization Log

Document any insights, failed approaches, or technical discoveries here. This ensures the system self-improves and future agents don't repeat mistakes.

## [2026-04-07] - Initial Ingestion & Research Agent Setup
- **Insight:** Pure vector search (Qdrant) is insufficient for exact data retrieval required for high-accuracy personalization. A hybrid approach (Postgres for exact JSON state, Qdrant for semantic similarity) is mandatory.
- **Insight:** Extended web research is extremely slow (10-30s per profile). This necessitates a task queue (like Redis) and background workers instead of a blocking linear script.
- **Insight:** The LLM must explicitly explain its confidence rationale so the user can provide actionable grading feedback. Without rationale, user feedback is blind and the system cannot self-correct.
- **Action:** Added `confidence_rationale` and `search_queries_used` to the Postgres schema and the interactive grading CLI.

## [2026-04-07] - Local LLM Hallucinations
- **Insight:** Smaller local models (like Mistral 8B) may hallucinate numeric scales, outputting percentages (e.g., 75, 85) instead of the requested 1-10 scale.
- **Action:** Added clamping and normalization logic to the `research_agent.py` parsing phase to automatically convert percentages back to the expected 1-10 integer scale.
