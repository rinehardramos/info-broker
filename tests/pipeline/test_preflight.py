from app.pipeline.preflight import extract, validate


def test_extract_does_not_treat_founder_as_first_person_evidence():
    result = extract(
        "Inspect the uploaded spreadsheet and identify likely SME founders who may need outsourced IT."
    )
    assert result.first_person_evidence is False


def test_validate_uploaded_spreadsheet_query_is_not_blocked_by_founder_word():
    result = validate(
        "Inspect the uploaded spreadsheet and identify likely SME founders who may need outsourced IT."
    )
    assert result.blocking is False
    assert result.first_question is None
