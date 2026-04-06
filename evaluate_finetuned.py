"""Phase 5: compare a fine-tuned model against the base model.

Reads the same alignment metric used by ``evaluate_grading.py`` and runs
the research agent twice — once with ``CHAT_MODEL_NAME`` (base) and once
with ``FINETUNED_MODEL_NAME`` (the fine-tune) — over a held-out set of
already-graded profiles. Prints per-model average alignment.

This is a thin wrapper that exists so the existing
``test_grading.py`` / ``evaluate_grading.py`` suite stays the
single source of truth for the accuracy metric.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics

import psycopg2
from dotenv import load_dotenv
from openai import OpenAI

from evaluate_grading import calculate_alignment_score
from security import sanitize_for_prompt

load_dotenv()

LM_STUDIO_BASE_URL = os.getenv("LM_STUDIO_BASE_URL", "http://localhost:1234/v1")
LM_STUDIO_API_KEY = os.getenv("LM_STUDIO_API_KEY", "lm-studio")
BASE_MODEL = os.getenv("CHAT_MODEL_NAME", "local-model")
FINETUNED_MODEL = os.getenv("FINETUNED_MODEL_NAME", "local-model-ft")

DB_NAME = os.getenv("POSTGRES_DB", "auto_marketer")
DB_USER = os.getenv("POSTGRES_USER", "user")
DB_PASSWORD = os.getenv("POSTGRES_PASSWORD", "password")
DB_HOST = os.getenv("POSTGRES_HOST", "localhost")
DB_PORT = os.getenv("POSTGRES_PORT", "5432")

client = OpenAI(base_url=LM_STUDIO_BASE_URL, api_key=LM_STUDIO_API_KEY)

EVAL_SYSTEM_PROMPT = (
    "You are an expert OSINT and business research agent. Reply with ONLY a "
    "JSON object: is_smb (bool), needs_outsourcing_prob (float), "
    "needs_cheap_labor_prob (float), searching_vendors_prob (float), "
    "research_summary (string), system_confidence_score (1-10 int), "
    "confidence_rationale (string)."
)


def fetch_eval_set(limit: int = 50):
    conn = psycopg2.connect(
        dbname=DB_NAME, user=DB_USER, password=DB_PASSWORD,
        host=DB_HOST, port=DB_PORT,
    )
    cur = conn.cursor()
    cur.execute("""
        SELECT first_name, last_name, headline, raw_data, user_grade
        FROM linkedin_profiles
        WHERE user_grade IS NOT NULL
        ORDER BY RANDOM() LIMIT %s
    """, (limit,))
    rows = cur.fetchall()
    conn.close()
    return rows


def run_model(model_name: str, profile_summary: dict):
    safe_input = sanitize_for_prompt(
        json.dumps(profile_summary, indent=2),
        label="profile",
        max_length=2000,
    )
    response = client.chat.completions.create(
        model=model_name,
        messages=[
            {"role": "system", "content": EVAL_SYSTEM_PROMPT},
            {"role": "user", "content": "Please research this profile:\n" + safe_input},
        ],
        temperature=0.0,
    )
    try:
        return json.loads(response.choices[0].message.content)
    except json.JSONDecodeError:
        return None


def evaluate(model_name: str, rows) -> float | None:
    scores = []
    for first, last, headline, raw_data, user_grade in rows:
        profile_summary = {
            "name": f"{first} {last}",
            "headline": headline,
            "about": raw_data.get("about", "") if isinstance(raw_data, dict) else "",
        }
        analysis = run_model(model_name, profile_summary)
        if not analysis:
            continue
        sys_conf = analysis.get("system_confidence_score")
        scores.append(calculate_alignment_score(sys_conf, user_grade))
    if not scores:
        return None
    return round(statistics.mean(scores), 2)


def main():
    parser = argparse.ArgumentParser(description="Compare base vs fine-tuned model alignment.")
    parser.add_argument("--limit", type=int, default=50, help="Number of graded profiles to sample")
    args = parser.parse_args()

    rows = fetch_eval_set(limit=args.limit)
    if not rows:
        print("No graded profiles found to evaluate against.")
        return

    print(f"Evaluating {len(rows)} graded profiles...\n")
    base_acc = evaluate(BASE_MODEL, rows)
    ft_acc = evaluate(FINETUNED_MODEL, rows)

    print("=" * 50)
    print(f"  Base model       ({BASE_MODEL}):  {base_acc}%")
    print(f"  Fine-tuned model ({FINETUNED_MODEL}):  {ft_acc}%")
    print("=" * 50)
    if base_acc is not None and ft_acc is not None:
        delta = ft_acc - base_acc
        verdict = "improvement" if delta > 0 else "regression" if delta < 0 else "tie"
        print(f"  Delta: {delta:+.2f} pp ({verdict})")


if __name__ == "__main__":
    main()
