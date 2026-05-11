from __future__ import annotations

import os
import tempfile

import pandas as pd

from app.sources.datastore import ingest_tabular_source, query_tabular_source, tabular_manifest_findings


def test_ingest_csv_writes_parquet_data_plane_without_row_values_in_manifest(monkeypatch):
    with tempfile.TemporaryDirectory() as root:
        monkeypatch.setenv("SOURCE_DATASTORE_ROOT", root)
        csv_path = os.path.join(root, "people.csv")
        pd.DataFrame([
            {"firstName": "Deb", "headline": "Founder & CEO helping SMEs", "emails/0/email": "deb@example.com"},
            {"firstName": "Alex", "headline": "Software engineer", "emails/0/email": "alex@example.com"},
        ]).to_csv(csv_path, index=False)

        manifest = ingest_tabular_source("source-1", "user-1", csv_path, "people.csv")

        assert manifest["storage"] == "data_plane"
        assert manifest["artifact_format"] == "parquet"
        assert manifest["row_count"] == 2
        assert os.path.exists(manifest["tables"][0]["artifact_path"])
        assert "deb@example.com" not in str(manifest)


def test_query_tabular_source_reads_parquet_artifact_not_original_file(monkeypatch):
    with tempfile.TemporaryDirectory() as root:
        monkeypatch.setenv("SOURCE_DATASTORE_ROOT", root)
        csv_path = os.path.join(root, "people.csv")
        pd.DataFrame([
            {
                "firstName": "Deb",
                "lastName": "Thomas",
                "headline": "Founder & CEO helping SMEs simplify renewals",
                "currentPosition/0/companyName": "Manage My Renewals",
                "companyWebsites/0/validEmailServer": "True",
                "emails/0/email": "deb@example.com",
            },
            {
                "firstName": "Alex",
                "lastName": "Smith",
                "headline": "Senior software engineer",
                "currentPosition/0/companyName": "Big SaaS",
                "companyWebsites/0/validEmailServer": "True",
                "emails/0/email": "alex@example.com",
            },
        ]).to_csv(csv_path, index=False)
        manifest = ingest_tabular_source("source-1", "user-1", csv_path, "people.csv")
        os.unlink(csv_path)

        results = query_tabular_source(
            {"id": "source-1", "filename": "people.csv", "manifest": manifest},
            "SME outsourced IT founder CEO valid email",
            limit=1,
        )

        assert results[0]["source_tool"] == "file_upload_row"
        assert results[0]["row_number"] == 1
        assert results[0]["row_data"]["firstName"] == "Deb"
        assert results[0]["row_data"]["emails/0/email"] == "deb@example.com"


def test_tabular_manifest_findings_are_schema_only(monkeypatch):
    with tempfile.TemporaryDirectory() as root:
        monkeypatch.setenv("SOURCE_DATASTORE_ROOT", root)
        csv_path = os.path.join(root, "people.csv")
        pd.DataFrame([{"name": "Private Person", "email": "secret@example.com"}]).to_csv(csv_path, index=False)
        manifest = ingest_tabular_source("source-1", "user-1", csv_path, "people.csv")

        findings = tabular_manifest_findings("people.csv", manifest)

        assert findings
        assert "name" in findings[0]["content"]
        assert "email" in findings[0]["content"]
        assert "Private Person" not in findings[0]["content"]
        assert "secret@example.com" not in findings[0]["content"]
