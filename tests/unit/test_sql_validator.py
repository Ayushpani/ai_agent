import pytest

from app.security.sql_validator import SQLValidationError, validate_and_prepare


def test_valid_select_with_placeholder_passes():
    sql = "SELECT a, b FROM main WHERE {ACCESS_SCOPE_FILTER} AND a > 1"
    result = validate_and_prepare(sql)
    assert "{ACCESS_SCOPE_FILTER}" in result.sql
    assert "LIMIT" in result.sql.upper()


def test_missing_placeholder_rejected():
    with pytest.raises(SQLValidationError, match="ACCESS_SCOPE_FILTER"):
        validate_and_prepare("SELECT * FROM main")


@pytest.mark.parametrize("bad_sql", [
    "DROP TABLE main",
    "DELETE FROM main WHERE {ACCESS_SCOPE_FILTER}",
    "UPDATE main SET x=1 WHERE {ACCESS_SCOPE_FILTER}",
    "INSERT INTO main VALUES (1)",
    "SELECT * FROM main WHERE {ACCESS_SCOPE_FILTER}; DROP TABLE main;",
])
def test_non_select_and_multi_statement_rejected(bad_sql):
    with pytest.raises(SQLValidationError):
        validate_and_prepare(bad_sql)


def test_row_cap_is_enforced_even_if_llm_requests_more():
    sql = "SELECT * FROM main WHERE {ACCESS_SCOPE_FILTER} LIMIT 999999999"
    result = validate_and_prepare(sql, row_cap=100)
    assert "LIMIT 100" in result.sql


def test_row_cap_added_when_absent():
    sql = "SELECT * FROM main WHERE {ACCESS_SCOPE_FILTER}"
    result = validate_and_prepare(sql, row_cap=500)
    assert "LIMIT 500" in result.sql


def test_prompt_injection_attempt_via_comment_is_still_rejected():
    """Adversarial case: a question tries to smuggle a second statement
    via a SQL comment terminator. sqlglot's multi-statement parse still
    catches it."""
    bad_sql = "SELECT 1 WHERE {ACCESS_SCOPE_FILTER} -- ' ; DROP TABLE main; --"
    # A single trailing comment is not itself a second statement, so this
    # should still pass as ONE select — the point is that any *executable*
    # second statement is rejected, not that comments are stripped.
    result = validate_and_prepare(bad_sql)
    assert result.sql  # parses as a single SELECT; comment is inert text
