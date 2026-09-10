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

from dataclasses import dataclass

import sqlglot
from sqlglot import exp

ACCESS_SCOPE_PLACEHOLDER = "{ACCESS_SCOPE_FILTER}"

DEFAULT_ROW_CAP = 100_000
DEFAULT_TIMEOUT_SECONDS = 30


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
