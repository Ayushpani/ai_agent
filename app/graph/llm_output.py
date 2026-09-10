"""Robust JSON extraction from raw LLM output.

Mirrors app/security/sql_validator.py's extract_sql_statement — a
"reasoning" model variant can emit a chain-of-thought preamble around
its actual JSON answer regardless of a "output ONLY JSON" instruction,
so json.loads(raw) directly is fragile. Used by the Router (doc §6.4.1)
and the SQL Generator's error-JSON path (doc §6.4.2).
"""
from __future__ import annotations

import json
import re

_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.IGNORECASE | re.DOTALL)


def extract_json_object(raw: str) -> dict | None:
    """Finds the first balanced {...} block that parses as JSON, checking
    fenced code blocks first (most likely to hold the real answer if a
    model used one), then the raw text. Returns None if nothing parses.
    """
    raw = raw.strip()
    candidates = [b.strip() for b in reversed(_FENCE_RE.findall(raw))] + [raw]

    for candidate in candidates:
        parsed = _first_balanced_json_object(candidate)
        if parsed is not None:
            return parsed
    return None


def _first_balanced_json_object(text: str) -> dict | None:
    start = text.find("{")
    while start != -1:
        depth = 0
        for i in range(start, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    try:
                        parsed = json.loads(text[start:i + 1])
                    except json.JSONDecodeError:
                        break
                    if isinstance(parsed, dict):
                        return parsed
                    break
        start = text.find("{", start + 1)
    return None
