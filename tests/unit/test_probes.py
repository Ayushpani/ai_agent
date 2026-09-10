"""The probe builder is the security boundary for the deep-research layer:
the research planner is an LLM, and the metric/dimension it picks are the
only LLM-chosen values that reach SQL. These tests pin the allow-listing
and the per-type SQL shape.
"""
import pytest

from app.models.schemas import ChartType, ProbeSpec, ProbeType
from app.security.sql_validator import ACCESS_SCOPE_PLACEHOLDER, validate_and_prepare
from app.tools.probes import ProbeBuildError, build_probe_sql, queryable_columns

ALL_TYPES = [
    (ProbeType.decompose_by, "BRANCH_NAME", ChartType.bar),
    (ProbeType.concentration, "REGION", ChartType.bar),
    (ProbeType.trend_by_segment, "REGION", ChartType.multi_line),
    (ProbeType.period_comparison, "PRODUCT", ChartType.grouped_bar),
    (ProbeType.distribution, None, ChartType.bar),
    (ProbeType.related_metric, None, ChartType.line),
]


def _spec(probe_type, dimension, metric="PRINCIPAL_OS"):
    return ProbeSpec(
        probe_type=probe_type, title="t", rationale="r", metric=metric, dimension=dimension
    )


@pytest.mark.parametrize("probe_type,dimension,expected_chart", ALL_TYPES)
def test_every_probe_type_builds_valid_scoped_sql(probe_type, dimension, expected_chart):
    sql, chart = build_probe_sql(_spec(probe_type, dimension), role="admin")

    assert chart.chart_type is expected_chart
    assert ACCESS_SCOPE_PLACEHOLDER in sql
    # Must survive the same validator the primary query goes through.
    validate_and_prepare(sql)


def test_trend_by_segment_scopes_the_outer_query_too():
    """Regression: the CTE was scoped but the outer aggregation was not,
    so a region-scoped user would have got top segments from their region
    and totals from every region."""
    sql, _ = build_probe_sql(_spec(ProbeType.trend_by_segment, "REGION"), role="admin")
    assert sql.count(ACCESS_SCOPE_PLACEHOLDER) == 2


def test_unknown_metric_is_rejected():
    with pytest.raises(ProbeBuildError, match="not in the caller's schema card"):
        build_probe_sql(_spec(ProbeType.decompose_by, "REGION", metric="NOT_A_COLUMN"), role="admin")


def test_sql_injection_via_metric_is_rejected():
    with pytest.raises(ProbeBuildError):
        build_probe_sql(
            _spec(ProbeType.decompose_by, "REGION", metric="PRINCIPAL_OS; DROP TABLE main"),
            role="admin",
        )


def test_role_denied_column_is_rejected_as_dimension():
    """DSA is visible to admin but denied to a region manager — the probe
    builder must refuse it for the role that cannot see it."""
    build_probe_sql(_spec(ProbeType.decompose_by, "DSA"), role="admin")

    with pytest.raises(ProbeBuildError, match="not in the caller's schema card"):
        build_probe_sql(_spec(ProbeType.decompose_by, "DSA"), role="region_manager")


def test_probe_type_needing_a_dimension_rejects_a_missing_one():
    with pytest.raises(ProbeBuildError, match="requires a dimension"):
        build_probe_sql(_spec(ProbeType.decompose_by, None), role="admin")


def test_queryable_columns_respects_role():
    admin = queryable_columns("admin")
    region = queryable_columns("region_manager")
    assert "DSA" in admin
    assert "DSA" not in region
    assert "PRINCIPAL_OS" in region


def test_generated_sql_keeps_line_breaks_for_display():
    """The SQL is shown to the employee and written into the workbook —
    one 400-character line is unreadable in both."""
    sql, _ = build_probe_sql(_spec(ProbeType.period_comparison, "PRODUCT"), role="admin")
    assert "\n" in sql
    assert not sql.startswith(" ")
