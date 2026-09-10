"""SQL validator — doc §9.5 (prompt-injection defense) and §2/§7.1 (run_sql).

Runs on every LLM-generated SQL string before it ever reaches DuckDB:
  1. Parse with sqlglot; reject anything that isn't a single SELECT.
  2. Require the literal {ACCESS_SCOPE_FILTER} placeholder in the WHERE
     clause (the LLM must not omit it — the substitution step depends on it).
  3. Enforce a row cap (LIMIT injection) and hand back a timeout for the
     caller to apply at the DuckDB session level.

This module has no LLM dependency and is unit-testable standalone.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

import sqlglot
from sqlglot import exp

ACCESS_SCOPE_PLACEHOLDER = "{ACCESS_SCOPE_FILTER}"

DEFAULT_ROW_CAP = 100_000
DEFAULT_TIMEOUT_SECONDS = 30

_FENCE_RE = re.compile(r"```(?:sql)?\s*(.*?)```", re.IGNORECASE | re.DOTALL)
# A "tempered dot" — (?!\n\s*\n). — matches any character, including a
# newline, as long as a blank line doesn't start at that position. This
# keeps the match from jumping across a paragraph break to reach a LATER
# unrelated SELECT's placeholder, which plain ".*?" with DOTALL would do.
_SELECT_WITH_PLACEHOLDER_RE = re.compile(
    r"(?is)select\b(?:(?!\n\s*\n).)*?" + re.escape(ACCESS_SCOPE_PLACEHOLDER)
    + r"(?:(?!\n\s*\n).)*?(?=\n\s*\n|```|$)"
)


def extract_sql_statement(raw: str) -> str | None:
    """Best-effort extraction of the actual SQL statement out of a raw
    LLM response that may not have followed the "output only SQL"
    instruction — most notably, "reasoning" model variants that emit a
    chain-of-thought preamble regardless of the system prompt. Returns
    None if nothing plausible is found, so the caller can fail with a
    clear error instead of feeding prose into the SQL parser.

    Preference order: a fenced ```sql ... ``` block that starts with
    SELECT, then the last SELECT-containing-the-placeholder run in the
    raw text (models that reason typically state their real answer last),
    then the raw text itself if it already looks like clean SQL.
    """
    raw = raw.strip()

    for block in reversed(_FENCE_RE.findall(raw)):
        block = block.strip()
        if re.match(r"(?i)^select\b", block) and _looks_like_sql(block):
            return block

    matches = list(_SELECT_WITH_PLACEHOLDER_RE.finditer(raw))
    for match in reversed(matches):
        candidate = match.group(0).strip()
        if _looks_like_sql(candidate):
            return candidate

    if re.match(r"(?i)^select\b", raw) and ACCESS_SCOPE_PLACEHOLDER in raw and _looks_like_sql(raw):
        return raw

    return None


def _looks_like_sql(candidate: str) -> bool:
    """A real SELECT always has a FROM clause; a reasoning model's prose
    ABOUT the instructions (e.g. 'Generate one SELECT statement, include
    {ACCESS_SCOPE_FILTER} in WHERE...') matches the SELECT+placeholder
    pattern but is not actually SQL — it has no FROM. This is the cheapest
    reliable signal to tell the two apart without a full parse attempt.
    """
    return bool(re.search(r"(?i)\bfrom\b", candidate))


class SQLValidationError(ValueError):
    pass


@dataclass
class ValidatedQuery:
    sql: str  # with row cap applied, placeholder still present
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS


def validate_and_prepare(
    sql: str,
    row_cap: int = DEFAULT_ROW_CAP,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    dialect: str = "duckdb",
) -> ValidatedQuery:
    """Raises SQLValidationError on any violation. Returns a query with a
    LIMIT clause applied (added if absent, tightened if the LLM's own
    LIMIT exceeds the cap).
    """
    sql = sql.strip().rstrip(";")

    if ACCESS_SCOPE_PLACEHOLDER not in sql:
        raise SQLValidationError(
            f"Generated SQL is missing the required {ACCESS_SCOPE_PLACEHOLDER} "
            f"placeholder. Refusing to execute unscoped queries."
        )

    # Parse with the placeholder swapped for a syntactically valid stand-in,
    # since sqlglot cannot parse the raw '{...}' token.
    parseable_sql = sql.replace(ACCESS_SCOPE_PLACEHOLDER, "1=1")

    try:
        statements = sqlglot.parse(parseable_sql, read=dialect)
    except Exception as e:  # sqlglot raises its own ParseError subclasses
        raise SQLValidationError(f"SQL failed to parse: {e}") from e

    if len(statements) != 1:
        raise SQLValidationError(
            f"Expected exactly one statement, found {len(statements)}. "
            f"Multi-statement payloads are rejected outright."
        )

    stmt = statements[0]
    if stmt is None or not isinstance(stmt, exp.Select):
        raise SQLValidationError(
            "Only a single read-only SELECT statement is permitted. "
            "DDL/DML/multi-statement input is rejected."
        )

    if stmt.args.get("into") is not None:
        raise SQLValidationError(
            "SELECT ... INTO (materializing a new table/view) is not a "
            "read-only query and is rejected."
        )

    forbidden_node_types = (
        exp.Insert, exp.Update, exp.Delete, exp.Create, exp.Drop,
        exp.Alter, exp.Merge, exp.Command,
    )
    for node in stmt.walk():
        node_obj = node[0] if isinstance(node, tuple) else node
        if isinstance(node_obj, forbidden_node_types):
            raise SQLValidationError(
                f"Forbidden SQL construct detected: {type(node_obj).__name__}"
            )

    existing_limit = stmt.args.get("limit")
    if existing_limit is not None:
        try:
            requested = int(existing_limit.expression.this)
        except (AttributeError, ValueError, TypeError):
            requested = row_cap
        if requested > row_cap:
            stmt.set("limit", exp.Limit(expression=exp.Literal.number(row_cap)))
    else:
        stmt.set("limit", exp.Limit(expression=exp.Literal.number(row_cap)))

    capped_sql = stmt.sql(dialect=dialect)
    # Restore the placeholder (sqlglot round-trips '1=1' verbatim, so swap back).
    capped_sql = capped_sql.replace("1 = 1", ACCESS_SCOPE_PLACEHOLDER).replace(
        "1=1", ACCESS_SCOPE_PLACEHOLDER
    )

    return ValidatedQuery(sql=capped_sql, timeout_seconds=timeout_seconds)
