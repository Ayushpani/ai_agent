from app.models.schemas import ChartType
from app.tools.chart import QueryShape, choose_chart_type


def _shape(**overrides):
    defaults = dict(
        has_time_dimension=False, category_column=None, category_cardinality=0,
        metric_columns=[], is_composition=False, has_forecast=False,
        is_single_scalar=False, time_column=None,
    )
    defaults.update(overrides)
    return QueryShape(**defaults)


def test_single_scalar_forces_kpi_callout_never_a_chart():
    spec = choose_chart_type(_shape(is_single_scalar=True, metric_columns=["aum"]))
    assert spec.chart_type == ChartType.kpi_callout


def test_forecast_forces_line_even_with_category_present():
    spec = choose_chart_type(_shape(
        has_forecast=True, has_time_dimension=True, time_column="month",
        metric_columns=["aum"], category_column="branch", category_cardinality=3,
    ))
    assert spec.chart_type == ChartType.line
    assert spec.forecast_forced is True


def test_time_dimension_chooses_line():
    spec = choose_chart_type(_shape(has_time_dimension=True, time_column="month", metric_columns=["pos"]))
    assert spec.chart_type == ChartType.line


def test_low_cardinality_category_chooses_bar():
    spec = choose_chart_type(_shape(category_column="branch", category_cardinality=5, metric_columns=["pos"]))
    assert spec.chart_type == ChartType.bar


def test_composition_under_seven_chooses_pie():
    spec = choose_chart_type(_shape(
        category_column="product", category_cardinality=4, is_composition=True, metric_columns=["pos"],
    ))
    assert spec.chart_type == ChartType.pie


def test_composition_over_seven_falls_back_to_bar_not_unreadable_pie():
    spec = choose_chart_type(_shape(
        category_column="branch", category_cardinality=20, is_composition=True, metric_columns=["pos"],
    ))
    assert spec.chart_type == ChartType.bar


def test_two_continuous_no_time_or_category_chooses_scatter():
    spec = choose_chart_type(_shape(metric_columns=["cibil", "ltv"]))
    assert spec.chart_type == ChartType.scatter
