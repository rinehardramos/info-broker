# Phase 5: Fine-tuning workflow

This document covers the end-to-end fine-tuning loop for the
research-agent model. The goal: take the human-graded profiles
accumulating in Postgres and use them to improve the underlying chat
model's accuracy on the SMB-targeting task.

## Prerequisites

- A Postgres instance with at least ~100 profiles graded `4/5` or `5/5`
  via `python research_agent.py --grade`. Fewer than 100 examples will
  technically work but yields a noisy fine-tune; more is better.
- LM Studio (or any OpenAI-compatible local serving stack) with
  fine-tuning support, **or** an OpenAI account if you choose to fine-tune
  a hosted model.
- The `uv`-managed venv: `uv sync --frozen --extra dev`.

## Step 1 — Export the dataset

```sh
uv run python export_dataset.py --output finetune_dataset.jsonl --min-grade 4
```

Selects every profile graded `>= --min-grade` and writes one chat-format
JSONL line per profile. Each line is an OpenAI-style `{"messages": [...]}`
record with three turns: system prompt, user request, assistant
ground-truth JSON. The system prompt is intentionally identical to the
one `research_agent.py` uses at inference time so the fine-tune sees
the task framed exactly the same way it will be at runtime.

Verify the export looks sane:

```sh
wc -l finetune_dataset.jsonl                    # one example per line
python3 -c "import json; [json.loads(l) for l in open('finetune_dataset.jsonl')]; print('valid')"
```

## Step 2 — Fine-tune

### Option A — LM Studio / local

Follow LM Studio's fine-tuning UI. Point the trainer at
`finetune_dataset.jsonl`, pick a base model, and let it run. When done,
note the new model identifier (e.g. `local-model-ft-2026-04-07`) and
load it for serving.

### Option B — OpenAI hosted

```sh
openai api fine_tunes.create -t finetune_dataset.jsonl -m gpt-4o-mini-2024-07-18
```

The CLI prints a job ID; poll it with `openai api fine_tunes.get -i <id>`.
The resulting model name follows the pattern
`ft:gpt-4o-mini-2024-07-18:org::abc123`.

## Step 3 — Configure the fine-tuned model

Add to your `.env`:

```sh
FINETUNED_MODEL_NAME=local-model-ft-2026-04-07   # or the OpenAI ft:... id
```

`evaluate_finetuned.py` reads this env var. The base model continues to
be read from `CHAT_MODEL_NAME`.

## Step 4 — Evaluate

```sh
uv run python evaluate_finetuned.py --limit 50
```

Samples 50 already-graded profiles from Postgres at random, runs both
the base and fine-tuned models against them, and prints the average
alignment score (the same metric used by `evaluate_grading.py` and
asserted in `test_grading.py`).

Output looks like:

```
==================================================
  Base model       (local-model):                42.50%
  Fine-tuned model (local-model-ft-2026-04-07):  68.75%
==================================================
  Delta: +26.25 pp (improvement)
```

Promote the fine-tune to production only if you see a meaningful (>5pp)
improvement that holds across multiple sample seeds.

## Step 5 — Promote (optional)

When the fine-tune wins, swap `CHAT_MODEL_NAME` in `.env` to the
fine-tuned identifier and restart the agent:

```sh
CHAT_MODEL_NAME=local-model-ft-2026-04-07
```

The Phase 1 ReAct loop, the Phase 2 episodic memory recall, the Phase 3
few-shot injection, and the Phase 4 critic agent all continue to work
unchanged — they only know about `CHAT_MODEL_NAME` and have no
fine-tune-specific code paths.

## Continuous loop

The full self-improvement loop is now closed:

1. `research_agent.py --run` produces analyses (Phase 1).
2. `research_agent.py --grade` collects human grades, which both:
   - get embedded into Qdrant episodic memory (Phase 2)
   - become future few-shot examples (Phase 3)
3. The critic gates each analysis at runtime (Phase 4).
4. Once enough 4/5 and 5/5 grades accumulate, `export_dataset.py` →
   fine-tune → `evaluate_finetuned.py` re-trains the underlying weights
   (Phase 5).
5. Promote the new model and start over.
