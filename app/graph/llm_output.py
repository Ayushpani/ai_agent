"""Cleaning up raw LLM output before it reaches a tool or the employee.

Mirrors app/security/sql_validator.py's extract_sql_statement — a
"reasoning" model variant can emit a chain-of-thought preamble around
its actual answer regardless of an "output ONLY ..." instruction, so
trusting the raw string is fragile. Used by the Router (doc §6.4.1), the
SQL Generator's error-JSON path (doc §6.4.2), and the Narrator (§6.4.4).
"""
from __future__ import annotations

import json
import re

_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.IGNORECASE | re.DOTALL)

# Lines that are pure scaffolding — the model announcing what it is about
# to do — and carry no content of their own.
_SCAFFOLD_LINE_RE = re.compile(
    r"^\s*(?:"
    r"let'?s\s+(?:craft|write|draft|begin|start)"
    r"|let\s+me\s+(?:craft|write|draft|begin|start|think)"
    r"|(?:here'?s|here\s+is)\s+(?:the|my)\s+(?:answer|response|draft|write-?up)"
    r"|draft"
    r"|final\s+answer"
    r"|findings?\s+in\s+order\s+of\s+importance"
    r"|notable\s+findings?"
    r"|in\s+order\s+of\s+importance"
    r")\s*[:.]?\s*$",
    re.IGNORECASE,
)

# Labels the model prefixes onto a line that DOES carry content — strip
# the label, keep the sentence after it.
_SCAFFOLD_PREFIX_RE = re.compile(
    r"^\s*(?:"
    r"direct\s+answer"
    r"|answer"
    r"|response"
    r"|summary"
    r"|final\s+answer"
    r")\s*:\s*",
    re.IGNORECASE,
)


def strip_scaffolding(text: str) -> str:
    """Removes a model's drafting scaffolding from prose meant to be shown
    to the employee verbatim.

    Observed in practice: a free-tier narrator opened its answer with
    "Let's craft:" followed by "Direct answer: ..." and "Findings in
    order of importance:", i.e. it wrote its plan for the answer into the
    answer. The prompt forbids this; weaker models do it anyway, so the
    guard is here rather than only in the instructions.

    Deliberately conservative — it only drops a line that is ENTIRELY
    scaffolding, and only strips a label prefix when real content follows
    on the same line. Nothing that could be a genuine sentence is removed.
    """
    lines = text.strip().splitlines()
    cleaned: list[str] = []

    for line in lines:
        if _SCAFFOLD_LINE_RE.match(line):
            continue
        cleaned.append(_SCAFFOLD_PREFIX_RE.sub("", line, count=1))

    # Collapse any blank-line run the removals opened up, and drop blank
    # lines that ended up leading the text.
    result = "\n".join(cleaned).strip()
    return re.sub(r"\n{3,}", "\n\n", result)


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
