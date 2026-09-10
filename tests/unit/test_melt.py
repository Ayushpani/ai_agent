import pandas as pd

from ingestion.melt import detect_monthly_column_groups, melt_monthly_groups


def test_detect_monthly_column_groups_finds_bounce_and_irac():
    columns = [
        "LOAN_AGREEMENT_NO", "PRODUCT",
        "Bounce Mar 26", "Bounce Apr 26", "Bounce May 26",
        "IRAC LAN Level Jul 26", "IRAC LAN Level Aug 26",
    ]
    groups = detect_monthly_column_groups(columns)
    assert set(groups.keys()) == {"Bounce", "IRAC LAN Level"}
    assert len(groups["Bounce"]) == 3
    assert len(groups["IRAC LAN Level"]) == 2


def test_single_month_column_is_not_a_group():
    columns = ["LOAN_AGREEMENT_NO", "Bounce Mar 26"]
    groups = detect_monthly_column_groups(columns)
    assert groups == {}


def test_melt_monthly_groups_produces_long_format():
    df = pd.DataFrame({
        "LOAN_AGREEMENT_NO": ["L1", "L2"],
        "Bounce Mar 26": [0, 1],
        "Bounce Apr 26": [1, 0],
        "PRODUCT": ["HL", "LAP"],
    })
    remainder, long_tables = melt_monthly_groups(df, id_column="LOAN_AGREEMENT_NO")

    assert "bounce" in long_tables
    assert set(remainder.columns) == {"LOAN_AGREEMENT_NO", "PRODUCT"}
    long_df = long_tables["bounce"]
    assert len(long_df) == 4
    assert set(long_df.columns) == {"LOAN_AGREEMENT_NO", "value", "month"}


def test_melt_handles_new_month_appended_upstream_without_code_change():
    """doc §12 risk: 'Melt logic misses a new monthly column group'."""
    df = pd.DataFrame({
        "LOAN_AGREEMENT_NO": ["L1"],
        "Bounce Mar 26": [0],
        "Bounce Sep 26": [1],  # a month never seen before, appended upstream
    })
    _, long_tables = melt_monthly_groups(df, id_column="LOAN_AGREEMENT_NO")
    assert len(long_tables["bounce"]) == 2
