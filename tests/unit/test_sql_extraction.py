from app.security.sql_validator import extract_sql_statement


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
