import json


def parse_llm_json(raw_response: str) -> dict:
    """
    Parses a JSON response from Claude, handling markdown code blocks.
    Used by all agents to avoid repeating the same parsing logic.
    """
    try:
        cleaned = raw_response.strip()
        if "```" in cleaned:
            parts = cleaned.split("```")
            for part in parts:
                part = part.strip()
                if part.startswith("json"):
                    part = part[4:].strip()
                if part.startswith("{"):
                    cleaned = part
                    break
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return {
            "error": "Failed to parse JSON response",
            "raw_response": raw_response
        }