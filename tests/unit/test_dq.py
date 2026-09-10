import pandas as pd

from app.tools.dq import data_quality_scan, sanity_check_trend


def test_empty_dataframe_flagged():
    flags = data_quality_scan(pd.DataFrame())
    assert any(f.kind == "empty_result" for f in flags)


def test_nulls_flagged_with_severity_scaled_to_pct():
    df = pd.DataFrame({"a": [1, None, None, None]})
    flags = data_quality_scan(df)
    null_flags = [f for f in flags if f.kind == "null_values"]
    assert len(null_flags) == 1
    assert null_flags[0].severity == "critical"  # 75% nulls


def test_duplicate_id_flagged():
    df = pd.DataFrame({"loan_id": ["L1", "L1", "L2"]})
    flags = data_quality_scan(df, id_column="loan_id")
    assert any(f.kind == "duplicate_id" for f in flags)


def test_sanity_check_trend_flags_single_point_dominance():
    s = pd.Series([100, 101, 102, 500, 501])  # one huge jump dominates
    flags = sanity_check_trend(s)
    assert any(f.kind == "single_point_dominance" for f in flags)


def test_sanity_check_trend_silent_for_smooth_series():
    s = pd.Series([100, 110, 121, 133, 146])
    flags = sanity_check_trend(s)
    assert flags == []
