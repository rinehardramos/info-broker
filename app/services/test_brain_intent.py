from unittest.mock import MagicMock, patch
from app.services.brain_intent import classify_intent


def _mock_response(text: str):
    msg = MagicMock()
    msg.content = [MagicMock(text=text)]
    return msg


def test_classify_list_intent():
    payload = '{"intent":"list","confidence":0.95,"rationale":"Query starts with list","enriched_query":null}'
    with patch("app.services.brain_intent._client") as mock_client:
        mock_client.messages.create.return_value = _mock_response(payload)
        result = classify_intent("list all anime in 2026")
    assert result.intent == "list"
    assert result.confidence == 0.95


def test_classify_strips_markdown_fences():
    payload = '```json\n{"intent":"lookup","confidence":0.9,"rationale":"Direct lookup","enriched_query":null}\n```'
    with patch("app.services.brain_intent._client") as mock_client:
        mock_client.messages.create.return_value = _mock_response(payload)
        result = classify_intent("what is GPT-5")
    assert result.intent == "lookup"
