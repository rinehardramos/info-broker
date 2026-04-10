import os
import json
import psycopg2
import uuid
from qdrant_client import QdrantClient
from qdrant_client.models import VectorParams, Distance, PointStruct
from dotenv import load_dotenv

from security import (
    safe_fetch_url,
    coerce_db_text,
    scrub_jsonb,
    JSON_CONTENT_TYPES,
    DEFAULT_EMBEDDING_INPUT_MAX,
    UnsafeURLError,
)

# Hard caps for hostile upstream data
MAX_APIFY_BYTES = 50 * 1024 * 1024  # 50 MiB on the dataset response
MAX_PROFILE_ID_LEN = 128
MAX_NAME_LEN = 256
MAX_HEADLINE_LEN = 1024
MAX_ABOUT_LEN = 8000

load_dotenv()

from llm_providers import build_client, embed_text  # noqa: E402 — after load_dotenv

APIFY_URL = os.getenv("APIFY_DATASET_URL")

DB_NAME = os.getenv("POSTGRES_DB", "info_broker")
DB_USER = os.getenv("POSTGRES_USER")
DB_PASSWORD = os.getenv("POSTGRES_PASSWORD")
DB_HOST = os.getenv("POSTGRES_HOST")
DB_PORT = os.getenv("POSTGRES_PORT")

QDRANT_HOST = os.getenv("QDRANT_HOST")
QDRANT_PORT = int(os.getenv("QDRANT_PORT"))

# Initialize clients
openai_client = build_client()
qdrant = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)

# Postgres setup
def setup_postgres():
    conn = psycopg2.connect(
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        host=DB_HOST,
        port=DB_PORT
    )
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS linkedin_profiles (
            id VARCHAR PRIMARY KEY,
            first_name VARCHAR,
            last_name VARCHAR,
            headline TEXT,
            about TEXT,
            raw_data JSONB
        )
    """)
    conn.commit()
    return conn

# Qdrant setup
def setup_qdrant():
    collection_name = "linkedin_profiles"
    if not qdrant.collection_exists(collection_name=collection_name):
        qdrant.create_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(size=768, distance=Distance.COSINE),
        )
    return collection_name

def get_embedding(text):
    return embed_text(text)

def ingest_data(overwrite: bool = False) -> dict:
    """Fetch profiles from Apify, write to Postgres + Qdrant.

    Returns a counts dict with keys: fetched, inserted, skipped, errors.
    When ``overwrite`` is True, existing rows are replaced via ON CONFLICT
    DO UPDATE; otherwise existing rows are preserved (DO NOTHING).
    """
    counts = {"fetched": 0, "inserted": 0, "skipped": 0, "errors": 0}
    conn = setup_postgres()
    cur = conn.cursor()
    collection_name = setup_qdrant()

    print("Fetching data from Apify...")
    try:
        response = safe_fetch_url(
            APIFY_URL,
            timeout=30,
            max_bytes=MAX_APIFY_BYTES,
            allowed_content_types=JSON_CONTENT_TYPES,
        )
    except UnsafeURLError as e:
        print(f"Refused unsafe APIFY_DATASET_URL: {e}")
        return counts
    data = response.json()
    if not isinstance(data, list):
        print("Apify response was not a list of profiles; aborting.")
        return counts

    counts["fetched"] = len(data)
    print(f"Fetched {len(data)} profiles. Ingesting...")

    if overwrite:
        insert_sql = """
            INSERT INTO linkedin_profiles (id, first_name, last_name, headline, about, raw_data)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (id) DO UPDATE SET
                first_name = EXCLUDED.first_name,
                last_name = EXCLUDED.last_name,
                headline = EXCLUDED.headline,
                about = EXCLUDED.about,
                raw_data = EXCLUDED.raw_data
        """
    else:
        insert_sql = """
            INSERT INTO linkedin_profiles (id, first_name, last_name, headline, about, raw_data)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (id) DO NOTHING
        """

    for i, profile in enumerate(data):
        if not isinstance(profile, dict):
            continue
        profile_id = coerce_db_text(profile.get("id"), max_length=MAX_PROFILE_ID_LEN)
        if not profile_id:
            continue

        first_name = coerce_db_text(profile.get("firstName"), max_length=MAX_NAME_LEN)
        last_name = coerce_db_text(profile.get("lastName"), max_length=MAX_NAME_LEN)
        headline = coerce_db_text(profile.get("headline"), max_length=MAX_HEADLINE_LEN)
        about = coerce_db_text(profile.get("about"), max_length=MAX_ABOUT_LEN)

        # Cap embedding input — prevents a single 5MB "about" field from
        # locking up the local embedding model.
        text_to_embed = f"{first_name} {last_name}\nHeadline: {headline}\nAbout: {about}"
        if len(text_to_embed) > DEFAULT_EMBEDDING_INPUT_MAX:
            text_to_embed = text_to_embed[:DEFAULT_EMBEDDING_INPUT_MAX]

        # Recursively strip NUL bytes / cap strings before pushing the
        # blob into a JSONB column (Postgres rejects \x00 in JSONB).
        safe_raw = scrub_jsonb(profile)

        try:
            print(f"Processing {i+1}/{len(data)}: {first_name} {last_name}")

            # Save to Postgres (parameterized — no SQL injection surface)
            cur.execute(
                insert_sql,
                (profile_id, first_name, last_name, headline, about, json.dumps(safe_raw)),
            )
            if cur.rowcount > 0:
                counts["inserted"] += 1
            else:
                counts["skipped"] += 1

            # Generate Embedding
            embedding = get_embedding(text_to_embed)

            # Save to Qdrant
            qdrant_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, profile_id))
            qdrant.upsert(
                collection_name=collection_name,
                points=[
                    PointStruct(
                        id=qdrant_id,
                        vector=embedding,
                        payload={
                            "apify_id": profile_id,
                            "first_name": first_name,
                            "last_name": last_name,
                            "headline": headline
                        }
                    )
                ]
            )
            
        except Exception as e:
            counts["errors"] += 1
            print(f"Error processing profile {profile_id}: {e}")

    conn.commit()
    cur.close()
    conn.close()
    print("Ingestion complete.")
    return counts

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Info-broker ingest CLI")
    parser.add_argument("--overwrite", action="store_true", help="Replace existing rows")
    args = parser.parse_args()
    print(ingest_data(overwrite=args.overwrite))
