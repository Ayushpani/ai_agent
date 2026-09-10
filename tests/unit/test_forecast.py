import numpy as np
import pandas as pd

from app.tools.forecast import forecast, forecast_feasibility, forecast_tracking_error


def test_feasibility_false_for_short_series():
    s = pd.Series([1, 2, 3])
    feasible, reason = forecast_feasibility(s)
    assert feasible is False
    assert reason is not None


def test_feasibility_true_for_adequate_series():
    s = pd.Series(range(6))
    feasible, reason = forecast_feasibility(s)
    assert feasible is True
    assert reason is None


def test_forecast_refuses_when_infeasible():
    s = pd.Series([1, 2, 3])
    result = forecast(s)
    assert result.feasible is False
    assert result.point_forecast == []


def test_forecast_produces_point_and_interval_for_adequate_series():
    rng = np.random.default_rng(0)
    s = pd.Series(100 + np.arange(12) * 2 + rng.normal(0, 1, 12))
    result = forecast(s, horizon=3)
    assert result.feasible is True
    assert len(result.point_forecast) == 3
    assert all(lo <= pt <= hi for lo, pt, hi in zip(result.interval_low, result.point_forecast, result.interval_high))
    assert result.model_used in {"SES", "Holt", "Holt-Winters", "auto_arima"}


def test_forecast_tracking_error_reports_bias_direction():
    result = forecast_tracking_error(prior_forecast=[100, 100], actual=[110, 110])
    assert result["bias_direction"] == "under-forecast"
    assert result["mape"] > 0
