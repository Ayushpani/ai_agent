import pandas as pd
import pytest

from app.tools.stats import (
    concentration_index,
    correlation,
    distribution_summary,
    outlier_flags,
    period_change,
    rank_top_n,
    zscore_latest,
)


def test_period_change_basic():
    s = pd.Series([100, 110])
    result = period_change(s, period=1)
    assert result.absolute_change == 10
    assert result.pct_change == 10.0


def test_period_change_insufficient_history_raises():
    s = pd.Series([100])
    with pytest.raises(ValueError):
        period_change(s, period=1)


def test_zscore_latest_buckets_extreme_correctly():
    s = pd.Series([10, 10, 10, 10, 10, 100])  # huge jump at the end
    result = zscore_latest(s)
    assert result.bucket == "extreme"


def test_zscore_latest_normal_for_stable_series():
    s = pd.Series([10, 11, 10, 9, 10, 10.5])
    result = zscore_latest(s)
    assert result.bucket in {"normal", "notable"}


def test_concentration_index_hhi_max_when_single_holder():
    s = pd.Series([100, 0, 0])
    assert concentration_index(s, method="hhi") == pytest.approx(1.0)


def test_concentration_index_hhi_low_when_evenly_spread():
    s = pd.Series([25, 25, 25, 25])
    assert concentration_index(s, method="hhi") == pytest.approx(0.25)


def test_gini_zero_for_perfect_equality():
    s = pd.Series([10, 10, 10, 10])
    assert concentration_index(s, method="gini") == pytest.approx(0.0, abs=1e-9)


def test_outlier_flags_iqr_detects_obvious_outlier():
    s = pd.Series([10, 11, 9, 10, 12, 500])
    flags = outlier_flags(s)
    assert flags.iloc[-1] == True  # noqa: E712
    assert not flags.iloc[0]


def test_rank_top_n_orders_and_limits():
    df = pd.DataFrame({"branch": ["A", "B", "C"], "aum": [10, 30, 20]})
    top = rank_top_n(df, "branch", "aum", n=2)
    assert list(top["branch"]) == ["B", "C"]


def test_correlation_significant_flag():
    a = pd.Series(range(30))
    b = pd.Series(range(30)) * 2 + 1
    result = correlation(a, b)
    assert result["coefficient"] == pytest.approx(1.0)
    assert result["significant"] is True


def test_distribution_summary_keys():
    s = pd.Series([1, 2, 3, 4, 5])
    summary = distribution_summary(s)
    assert set(summary.keys()) == {"mean", "median", "std", "p10", "p25", "p75", "p90", "skew"}
