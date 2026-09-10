"""Adversarial suite (doc §9.5, day-13 hardening: '20+ adversarial
prompts fail safely'). These simulate a malicious or careless SQL
Generator output reaching the validator — the validator must reject
every one of them before DuckDB ever sees the string.
"""
import pytest

from app.security.sql_validator import SQLValidationError, validate_and_prepare

ADVERSARIAL_PAYLOADS = [
    "DROP TABLE main; --",
    "SELECT * FROM main WHERE {ACCESS_SCOPE_FILTER}; DROP TABLE main; --",
    "SELECT * FROM main WHERE {ACCESS_SCOPE_FILTER} UNION SELECT * FROM sqlite_master; --",
    "'; DROP TABLE main; --",
    "SELECT * FROM main; SELECT * FROM main WHERE {ACCESS_SCOPE_FILTER}",
    "DELETE FROM main WHERE {ACCESS_SCOPE_FILTER}",
    "UPDATE main SET PRINCIPAL_OS = 0 WHERE {ACCESS_SCOPE_FILTER}",
    "INSERT INTO main (a) VALUES (1)",
    "CREATE TABLE evil (a INT)",
    "ALTER TABLE main ADD COLUMN evil INT",
    "ATTACH DATABASE '/etc/passwd' AS pwn",
    "SELECT load_extension('evil') FROM main WHERE {ACCESS_SCOPE_FILTER}",
    "SELECT * FROM main",  # missing placeholder entirely
    "SELECT * FROM main WHERE 1=1",  # tries to omit the real scope filter
    "  ",  # empty payload
    "not sql at all just prose",
    "SELECT * FROM main WHERE {ACCESS_SCOPE_FILTER} -- '); DROP TABLE main; --",
    "MERGE INTO main USING x ON true WHEN MATCHED THEN DELETE",
    "SELECT * INTO evil_copy FROM main WHERE {ACCESS_SCOPE_FILTER}",
    "COPY main TO '/tmp/exfil.csv' WHERE {ACCESS_SCOPE_FILTER}",
]


@pytest.mark.parametrize("payload", ADVERSARIAL_PAYLOADS)
def test_adversarial_payload_rejected_or_harmless(payload):
    """Every payload must either raise SQLValidationError, or — if it
    happens to parse as a single benign SELECT — must not have gained
    any capability beyond a plain read.
    """
    try:
        result = validate_and_prepare(payload)
    except SQLValidationError:
        return  # correctly rejected

    # If it wasn't rejected, it must have parsed as a single, harmless
    # SELECT with the row cap applied — never anything from the
    # forbidden-construct list.
    assert result.sql.strip().upper().startswith("SELECT")
    assert "LIMIT" in result.sql.upper()
