"""Phase 5: dump high-graded profiles into an OpenAI fine-tuning JSONL.

Selects every profile graded 4/5 or 5/5 and emits one chat-format
JSONL line per profile of the form:

    {"messages": [
        {"role": "system", "content": "<system prompt>"},
        {"role": "user", "content": "Please research this profile:\\n<profile>"},
        {"role": "assistant", "content": "<analysis JSON>"}
    ]}

This matches the OpenAI / LM Studio fine-tuning chat format. See
``docs/fine-tuning.md`` for the end-to-end workflow.
"""

from __future__ import annotations

import argparse
import json
import os

import psycopg2
from dotenv import load_dotenv

from security import coerce_db_text

load_dotenv()

DB_NAME = os.getenv("POSTGRES_DB", "auto_marketer")
DB_USER = os.getenv("POSTGRES_USER", "user")
DB_PASSWORD = os.getenv("POSTGRES_PASSWORD", "password")
DB_HOST = os.getenv("POSTGRES_HOST", "localhost")
DB_PORT = os.getenv("POSTGRES_PORT", "5432")

# Mirrors the system prompt fragment used by research_agent so the
# fine-tuned model learns the same task framing.
TRAINING_SYSTEM_PROMPT = (
    "You are an expert OSINT and business research agent. You research a "
    "LinkedIn profile to determine if they are a target for our B2B "
    "marketing. Reply with a JSON object containing is_smb (bool), "
    "needs_outsourcing_prob (float), needs_cheap_labor_prob (float), "
    "searching_vendors_prob (float), research_summary (string), "
    "system_confidence_score (1-10 int), and confidence_rationale (string)."
)

MIN_GRADE = 4  # only 4/5 and 5/5 examples are used for training


def fetch_training_rows(min_grade: int = MIN_GRADE):
    conn = psycopg2.connect(
        dbname=DB_NAME, user=DB_USER, password=DB_PASSWORD,
        host=DB_HOST, port=DB_PORT,
    )
    cur = conn.cursor()
    cur.execute("""
        SELECT first_name, last_name, headline, raw_data,
               is_smb, needs_outsourcing_prob, needs_cheap_labor_prob,
               searching_vendors_prob, research_summary,
               system_confidence_score, confidence_rationale, user_grade
        FROM linkedin_profiles
        WHERE user_grade >= %s AND research_summary IS NOT NULL
    """, (min_grade,))
    rows = cur.fetchall()
    conn.close()
    return rows


def row_to_chat_example(row) -> dict:
    """Convert one DB row into an OpenAI fine-tuning chat example."""
    (first, last, headline, raw_data, is_smb, out_p, cheap_p, vend_p,
     summary, conf, rationale, _grade) = row

    profile_input = {
        "name": coerce_db_text(f"{first} {last}", max_length=200),
        "headline": coerce_db_text(headline, max_length=500),
    }
    if isinstance(raw_data, dict):
        about = raw_data.get("about")
        if about:
            profile_input["about"] = coerce_db_text(about, max_length=2000)
        if raw_data.get("currentPosition"):
            company = raw_data["currentPosition"][0].get("companyName")
            if company:
                profile_input["company_name"] = coerce_db_text(company, max_length=200)

    assistant_output = {
        "is_smb": bool(is_smb) if is_smb is not None else None,
        "needs_outsourcing_prob": float(out_p) if out_p is not None else None,
        "needs_cheap_labor_prob": float(cheap_p) if cheap_p is not None else None,
        "searching_vendors_prob": float(vend_p) if vend_p is not None else None,
        "research_summary": coerce_db_text(summary, max_length=1500),
        "system_confidence_score": int(conf) if conf is not None else None,
        "confidence_rationale": coerce_db_text(rationale, max_length=1000),
    }

    return {
        "messages": [
            {"role": "system", "content": TRAINING_SYSTEM_PROMPT},
            {"role": "user", "content": "Please research this profile:\n" + json.dumps(profile_input, indent=2)},
            {"role": "assistant", "content": json.dumps(assistant_output)},
        ]
    }


def export_jsonl(output_path: str, min_grade: int = MIN_GRADE) -> int:
    rows = fetch_training_rows(min_grade=min_grade)
    if not rows:
        print(f"No profiles graded >= {min_grade}/5 found. Nothing to export.")
        return 0
    with open(output_path, "w", encoding="utf-8") as f:
        for row in rows:
            example = row_to_chat_example(row)
            f.write(json.dumps(example, ensure_ascii=False) + "\n")
    print(f"Exported {len(rows)} fine-tuning examples to {output_path}")
    return len(rows)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Export graded profiles as a fine-tuning JSONL.")
    parser.add_argument("--output", default="finetune_dataset.jsonl", help="Output JSONL path")
    parser.add_argument("--min-grade", type=int, default=MIN_GRADE, help="Minimum user_grade to include (1-5)")
    args = parser.parse_args()
    export_jsonl(args.output, min_grade=args.min_grade)
