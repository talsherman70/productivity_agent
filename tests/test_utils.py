"""
Tests for app/core/utils.py — the shared JSON parser.

Claude sometimes wraps JSON in markdown code blocks, adds extra text,
or returns broken JSON. All of these cases must be handled gracefully.
"""
from app.core.utils import parse_llm_json


class TestParseLlmJson:
    def test_plain_json_string(self):
        raw = '{"intent": "new_goal", "goal": "test"}'
        result = parse_llm_json(raw)
        assert result["intent"] == "new_goal"
        assert result["goal"] == "test"

    def test_json_in_markdown_code_block(self):
        raw = '```json\n{"intent": "new_goal", "goal": "test"}\n```'
        result = parse_llm_json(raw)
        assert result["intent"] == "new_goal"

    def test_json_in_plain_code_block(self):
        raw = '```\n{"intent": "other"}\n```'
        result = parse_llm_json(raw)
        assert result["intent"] == "other"

    def test_json_with_leading_and_trailing_whitespace(self):
        raw = '   \n{"key": "value"}\n   '
        result = parse_llm_json(raw)
        assert result["key"] == "value"

    def test_invalid_json_returns_error_dict(self):
        raw = "this is not json at all"
        result = parse_llm_json(raw)
        assert "error" in result
        assert "raw_response" in result

    def test_empty_string_returns_error_dict(self):
        result = parse_llm_json("")
        assert "error" in result

    def test_partial_json_returns_error_dict(self):
        raw = '{"key": "value"'  # missing closing brace
        result = parse_llm_json(raw)
        assert "error" in result

    def test_raw_response_preserved_on_error(self):
        raw = "not json"
        result = parse_llm_json(raw)
        assert result["raw_response"] == "not json"

    def test_nested_json_parsed_correctly(self):
        raw = '{"tasks": [{"id": 1, "title": "Task one"}]}'
        result = parse_llm_json(raw)
        assert result["tasks"][0]["title"] == "Task one"

    def test_json_with_extra_text_before_code_block(self):
        raw = 'Here is the result:\n```json\n{"status": "ok"}\n```'
        result = parse_llm_json(raw)
        assert result["status"] == "ok"
