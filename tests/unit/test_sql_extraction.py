from app.security.sql_validator import extract_sql_statement, validate_and_prepare


def test_cte_is_not_severed_at_its_inner_select():
    """Regression: a model wrote "WITH latest AS (SELECT ...) SELECT ..."
    and extraction anchored on the SELECT *inside* the CTE, dropping the
    "WITH latest AS (" prefix and leaving a dangling ")". The query then
    died with "Invalid expression / Unexpected token"."""
    raw = (
        "WITH latest AS (\n"
        "  SELECT max(snapshot_month) AS max_snap FROM main\n"
        ")\n"
        "SELECT m.snapshot_month, SUM(m.AUM_90PLUS_FINANCE_OWNSHARE) AS aum\n"
        "FROM main m\n"
        "WHERE m.STATE = 'Maharashtra' AND {ACCESS_SCOPE_FILTER}\n"
        "GROUP BY m.snapshot_month"
    )
    extracted = extract_sql_statement(raw)

    assert extracted is not None
    assert extracted.strip().upper().startswith("WITH")
    # The whole thing must survive the real validator, not merely look right.
    validate_and_prepare(extracted)


def test_cte_survives_a_reasoning_preamble_and_trailing_prose():
    raw = (
        "Let me think about this. I need the latest month first.\n\n"
        "WITH latest AS (SELECT max(snapshot_month) AS s FROM main)\n"
        "SELECT snapshot_month, SUM(PRINCIPAL_OS) AS pos\n"
        "FROM main WHERE {ACCESS_SCOPE_FILTER} GROUP BY snapshot_month\n\n"
        "That should give the trend."
    )
    extracted = extract_sql_statement(raw)

    assert extracted is not None
    assert extracted.strip().upper().startswith("WITH")
    assert "That should give the trend" not in extracted
    validate_and_prepare(extracted)


def test_group_by_and_order_by_are_not_truncated():
    """The extractor tries the longest slice first, so trailing clauses
    stay attached rather than being cut at the first boundary."""
    raw = (
        "SELECT snapshot_month, SUM(PRINCIPAL_OS) AS pos FROM main "
        "WHERE {ACCESS_SCOPE_FILTER} GROUP BY snapshot_month ORDER BY snapshot_month"
    )
    extracted = extract_sql_statement(raw)
    assert extracted is not None
    assert "ORDER BY" in extracted.upper()


def test_clean_sql_response_extracted_as_is():
    raw = "SELECT a FROM main WHERE {ACCESS_SCOPE_FILTER}"
    assert extract_sql_statement(raw) == raw


def test_fenced_sql_block_extracted():
    raw = "Sure, here you go:\n```sql\nSELECT a FROM main WHERE {ACCESS_SCOPE_FILTER}\n```\nHope that helps!"
    assert extract_sql_statement(raw) == "SELECT a FROM main WHERE {ACCESS_SCOPE_FILTER}"


def test_reasoning_preamble_before_final_sql_is_skipped():
    raw = (
        "Let me think through this step by step.\n"
        "1. The user wants trend data.\n"
        "2. I need to use the AUM_90PLUS_FINANCE_OWNSHARE column.\n\n"
        "SELECT snapshot_month, SUM(AUM_90PLUS_FINANCE_OWNSHARE) AS aum "
        "FROM main WHERE STATE='Maharashtra' AND {ACCESS_SCOPE_FILTER} "
        "GROUP BY snapshot_month ORDER BY snapshot_month"
    )
    extracted = extract_sql_statement(raw)
    assert extracted is not None
    assert extracted.strip().upper().startswith("SELECT")
    assert "{ACCESS_SCOPE_FILTER}" in extracted


def test_pure_reasoning_dump_with_no_final_sql_returns_none():
    """The exact failure mode hit in practice: a reasoning model that gets
    cut off mid-thought and never reaches an actual SQL statement."""
    raw = (
        "Here's a thinking process:\n\n"
        "1. Analyze user input...\n"
        "2. Identify key requirements...\n"
        "The main table doesn't seem to have a date column in the listed "
        "domains. However, the schema might imply that main table has all "
        "these columns, but they're organized into domains. Th"
    )
    assert extract_sql_statement(raw) is None


def test_reasoning_prose_describing_instructions_is_not_mistaken_for_sql():
    """A reasoning model that gets cut off can produce text like 'Generate
    one SELECT statement, include {ACCESS_SCOPE_FILTER} in WHERE...' —
    that matches SELECT + placeholder textually but has no FROM clause,
    so it is not actually SQL and must not be returned as if it were."""
    raw = (
        "Here's a thinking process:\n\n"
        "1. Analyze the task: Generate exactly one DuckDB SELECT statement, "
        "include {ACCESS_SCOPE_FILTER} in WHERE, explicit aliases, GROUP BY "
        "time period ascending\n\n"
        "The main table doesn't seem to have a date column in the listed "
        "domains. However, the schema might imply that main table has all "
        "these columns, but they're organized into domains. Th"
    )
    assert extract_sql_statement(raw) is None


def test_multiple_select_mentions_prefers_the_one_with_placeholder():
    raw = (
        "I could SELECT * FROM wrong_table but that's not scoped.\n\n"
        "SELECT a FROM main WHERE {ACCESS_SCOPE_FILTER}"
    )
    extracted = extract_sql_statement(raw)
    assert extracted == "SELECT a FROM main WHERE {ACCESS_SCOPE_FILTER}"
