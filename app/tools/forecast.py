"""Forecasting tools (doc §7.3). Deterministic, backtestable — model
chosen per-series by hold-out MAPE, never by the LLM.
"""
from __future__ import annotations

import warnings

import numpy as np
import pandas as pd
from statsmodels.tsa.holtwinters import ExponentialSmoothing, SimpleExpSmoothing

from app.models.schemas import ForecastResult

MIN_POINTS_FOR_FORECAST = 4


def forecast_feasibility(series: pd.Series) -> tuple[bool, str | None]:
    """Called before any forecast attempt. Fewer than ~4-6 points ->
    feasible=False, so narration says so honestly instead of producing a
    confident-sounding forecast off two data points.
    """
    n = len(series.dropna())
    if n < MIN_POINTS_FOR_FORECAST:
        return False, (
            f"Only {n} historical points available; at least "
            f"{MIN_POINTS_FOR_FORECAST} are required for a defensible forecast."
        )
    return True, None


def _mape(actual: np.ndarray, predicted: np.ndarray) -> float:
    actual, predicted = np.asarray(actual, dtype=float), np.asarray(predicted, dtype=float)
    mask = actual != 0
    if not mask.any():
        return float("inf")
    return float(np.mean(np.abs((actual[mask] - predicted[mask]) / actual[mask])) * 100)


def _backtest_holdout(series: pd.Series, n_holdout: int) -> pd.Series:
    return series.iloc[:-n_holdout] if n_holdout > 0 else series


def forecast(series: pd.Series, horizon: int = 3) -> ForecastResult:
    """Backtests SES / Holt / Holt-Winters against the last 1-3 held-out
    points; picks the winner by MAPE; returns a point forecast, an 80%
    interval, the model used, and its backtest MAPE.

    auto_arima (pmdarima) is included as a fourth candidate when the
    optional pmdarima dependency is installed (doc §4 tech stack); it is
    skipped gracefully otherwise so the POC has no hard dependency on a
    heavier, less-portable package.
    """
    feasible, reason = forecast_feasibility(series)
    if not feasible:
        return ForecastResult(
            horizon=horizon,
            point_forecast=[],
            interval_low=[],
            interval_high=[],
            model_used="none",
            backtest_mape=float("nan"),
            feasible=False,
            feasibility_reason=reason,
        )

    n_holdout = min(3, max(1, len(series) // 4))
    train = _backtest_holdout(series, n_holdout)
    holdout_actual = series.iloc[-n_holdout:].to_numpy()

    candidates: dict[str, float] = {}
    fitted_models: dict[str, object] = {}

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")

        try:
            ses = SimpleExpSmoothing(train, initialization_method="estimated").fit()
            pred = ses.forecast(n_holdout).to_numpy()
            candidates["SES"] = _mape(holdout_actual, pred)
            fitted_models["SES"] = ses
        except Exception:
            pass

        try:
            holt = ExponentialSmoothing(
                train, trend="add", initialization_method="estimated"
            ).fit()
            pred = holt.forecast(n_holdout).to_numpy()
            candidates["Holt"] = _mape(holdout_actual, pred)
            fitted_models["Holt"] = holt
        except Exception:
            pass

        if len(train) >= 2 * 12:
            try:
                hw = ExponentialSmoothing(
                    train, trend="add", seasonal="add", seasonal_periods=12,
                    initialization_method="estimated",
                ).fit()
                pred = hw.forecast(n_holdout).to_numpy()
                candidates["Holt-Winters"] = _mape(holdout_actual, pred)
                fitted_models["Holt-Winters"] = hw
            except Exception:
                pass

        try:
            import pmdarima as pm

            arima = pm.auto_arima(train, suppress_warnings=True, error_action="ignore")
            pred = arima.predict(n_holdout)
            candidates["auto_arima"] = _mape(holdout_actual, pred)
            fitted_models["auto_arima"] = arima
        except ImportError:
            pass
        except Exception:
            pass

    if not candidates:
        return ForecastResult(
            horizon=horizon,
            point_forecast=[],
            interval_low=[],
            interval_high=[],
            model_used="none",
            backtest_mape=float("nan"),
            feasible=False,
            feasibility_reason="All candidate models failed to fit this series.",
        )

    best_name = min(candidates, key=candidates.get)
    best_mape = candidates[best_name]

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        if best_name == "SES":
            final_model = SimpleExpSmoothing(series, initialization_method="estimated").fit()
            point = final_model.forecast(horizon).to_numpy()
            resid_std = float(np.std(final_model.resid))
        elif best_name == "Holt":
            final_model = ExponentialSmoothing(
                series, trend="add", initialization_method="estimated"
            ).fit()
            point = final_model.forecast(horizon).to_numpy()
            resid_std = float(np.std(final_model.resid))
        elif best_name == "Holt-Winters":
            final_model = ExponentialSmoothing(
                series, trend="add", seasonal="add", seasonal_periods=12,
                initialization_method="estimated",
            ).fit()
            point = final_model.forecast(horizon).to_numpy()
            resid_std = float(np.std(final_model.resid))
        else:  # auto_arima
            import pmdarima as pm

            final_model = pm.auto_arima(series, suppress_warnings=True, error_action="ignore")
            point = np.asarray(final_model.predict(horizon))
            resid_std = float(np.std(final_model.resid()))

    z_80 = 1.2816
    margin = z_80 * resid_std

    return ForecastResult(
        horizon=horizon,
        point_forecast=[round(float(v), 4) for v in point],
        interval_low=[round(float(v - margin), 4) for v in point],
        interval_high=[round(float(v + margin), 4) for v in point],
        model_used=best_name,
        backtest_mape=round(best_mape, 4),
        feasible=True,
    )


def forecast_tracking_error(prior_forecast: list[float], actual: list[float]) -> dict:
    """Compares reality to what was previously predicted for this series —
    a senior-analyst check a naive pipeline would never surface.
    """
    if len(prior_forecast) != len(actual):
        raise ValueError("prior_forecast and actual must be the same length")

    mape = _mape(np.array(actual), np.array(prior_forecast))
    errors = np.array(actual) - np.array(prior_forecast)
    return {
        "mape": round(mape, 4),
        "mean_error": round(float(errors.mean()), 4),
        "bias_direction": "over-forecast" if errors.mean() < 0 else "under-forecast",
    }
