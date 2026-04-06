# Agents and prompts

This page documents the prompt machinery inside `research_agent.py`. For the high-level component diagram see [architecture-and-agents.md](architecture-and-agents.md).

## The ReAct loop

`analyze_profile_with_react(profile_summary, few_shot=None)` is the researcher. It runs up to four LLM turns per profile (3 searches + 1 final answer) with `temperature=0.1`. Every turn the LLM must reply with one of two JSON objects:

```json
{"action": "search", "query": "Company Name location"}
```

or:

```json
{
  "action": "final",
  "is_smb": true,
  "needs_outsourcing_prob": 0.7,
  "needs_cheap_labor_prob": 0.4,
  "searching_vendors_prob": 0.3,
  "research_summary": "string",
  "system_confidence_score": 8,
  "confidence_rationale": "string"
}
```

Any other output breaks the loop. A `search` action calls `search_web` (DuckDuckGo via `ddgs`, sanitized through `validate_search_query`), then `scrape_url` on the top result (SSRF-checked via `safe_fetch_url`, HTML-only, 1500-char cap). The results and scraped page are appended as a `user` message for the next turn. On `final`, the agent clamps `system_confidence_score` to 1-10 (dividing by 10 if the model emits a percentage) and returns.

## Sanitization fences

All untrusted text that enters a prompt passes through `sanitize_for_prompt`, which:

1. Strips ASCII control chars (keeping `\n` and `\t`).
2. Caps length.
3. Wraps the result in `<<<BEGIN_{LABEL}>>> ... <<<END_{LABEL}>>>`.

The system prompt explicitly instructs the model that anything inside those fences is data, not instructions. Labels currently used: `profile`, `few_shot_best`, `few_shot_worst`, `past_mistake_N`, `search_result_N`, `scraped_page_N`, `analysis`.

## Episodic memory recall

Before the first researcher turn, `recall_similar_mistakes(profile_text)` runs a Qdrant vector search against the `user_feedback` collection, filtered to `grade <= LOW_GRADE_THRESHOLD` (3), and returns up to `RECALL_TOP_K` (3) hits. Each hit becomes one fenced warning appended to the system prompt:

```
Warnings from past mistakes (the analyst previously rated similar
profiles poorly with the following corrections — avoid repeating them):
<<<BEGIN_PAST_MISTAKE_1>>>
#1 (past grade 2/5) feedback: ...
<<<END_PAST_MISTAKE_1>>>
```

Memory is written by `save_grading_to_memory`, invoked at the end of `interactive_grading` and by `--backfill-memory` for historical rows.

## Few-shot injection

`fetch_few_shot_examples(cur)` queries Postgres for one random `user_grade = 5` profile and one random `user_grade = 1` profile that both have a non-null `research_summary`. `_format_few_shot_block` renders them as two fenced JSON blocks — a "PERFECT example" and a "FAILED example" — that get appended to the system prompt after the past-mistakes warnings. Examples are capped at 1200 chars each to protect the local model's context window.

## Critic agent

`critic_agent(profile_summary, analysis, past_mistakes=None)` is a second LLM call at `temperature=0.0`. Its system prompt asks for exactly:

```json
{"approved": true, "rationale": "one or two sentences"}
```

`process_pending_profiles` runs the researcher, runs the critic, and retries the researcher once if the critic rejects. On the second rejection the analysis is kept anyway (fail-open). Critic errors, non-JSON output, and exceptions all fail-open — the critic is an extra safety check, not a gate, and an outage must not block the pipeline.

## Prompt structure

Each research invocation builds a two-message chat:

- `role: system` — the base research prompt + security instructions + warnings block + few-shot block.
- `role: user` — `"Please research this profile:\n" + sanitize_for_prompt(profile_summary)`.

Subsequent turns append `assistant` (the model's JSON reply) and `user` (sanitized search results) messages in pairs.

The fine-tuning exporter (`export_dataset.py`) constructs the same structure — system / user / assistant — using a condensed system prompt defined in `TRAINING_SYSTEM_PROMPT`. Keeping the training framing close to the inference framing is intentional; see [fine-tuning.md](fine-tuning.md).

## Tuning knobs

| Constant | File | Purpose |
|---|---|---|
| `LOW_GRADE_THRESHOLD = 3` | `research_agent.py` | Max grade considered a "mistake" for memory recall. |
| `RECALL_TOP_K = 3` | `research_agent.py` | Max number of past mistakes injected per run. |
| `EMBEDDING_DIM = 768` | `research_agent.py` | Must match the LM Studio embedding model. |
| `DEFAULT_PROMPT_SANITIZE_MAX = 4000` | `security.py` | Default per-field cap for fenced prompt text. |
| `MAX 4 iterations` | `analyze_profile_with_react` | ReAct turn budget per profile. |
| `MIN_GRADE = 4` | `export_dataset.py` | Minimum grade to qualify as training data. |
