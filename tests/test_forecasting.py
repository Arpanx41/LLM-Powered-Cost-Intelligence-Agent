"""Tests for forecasting service."""
from datetime import date, timedelta

import pytest

from app.services.forecasting import (
    calculate_mape,
    generate_full_forecast,
    simple_moving_average_forecast,
    validate_forecast_mape,
)


def make_daily_costs(num_days: int, base: float = 100.0, trend_per_day: float = 0.0) -> list:
    """Build synthetic daily cost series."""
    start = date(2026, 1, 1)
    costs = []
    for i in range(num_days):
        value = base + (trend_per_day * i)
        # Deterministic "noise" via sine to keep tests stable
        noise = 5.0 * ((i % 7) / 6 - 0.5)
        costs.append({
            "date": start + timedelta(days=i),
            "cost": max(0.0, value + noise),
        })
    return costs


class TestSimpleMovingAverage:
    def test_insufficient_data_returns_error(self):
        result = simple_moving_average_forecast(make_daily_costs(10), horizon_days=30, window_size=30)
        assert "error" in result
        assert result["forecast"] == {}

    def test_flat_series_forecast_is_flat(self):
        data = make_daily_costs(60, base=100.0)
        result = simple_moving_average_forecast(data, horizon_days=7, window_size=30)
        assert "error" not in result
        values = list(result["forecast"].values())
        assert len(values) == 7
        # Flat series with no trend should forecast near the mean
        assert all(abs(v - 100.0) < 10.0 for v in values)

    def test_upward_trend_produces_positive_trend(self):
        data = make_daily_costs(90, base=50.0, trend_per_day=1.0)
        result = simple_moving_average_forecast(data, horizon_days=14, window_size=30)
        assert result["trend_per_day"] > 0
        values = list(result["forecast"].values())
        # Forecasts should be non-decreasing
        assert values == sorted(values)

    def test_forecast_dates_continue_after_last_date(self):
        data = make_daily_costs(60)
        result = simple_moving_average_forecast(data, horizon_days=3, window_size=30)
        last_date = max(d["date"] for d in data)
        expected_first = (last_date + timedelta(days=1)).isoformat()
        assert expected_first in result["forecast"]

    def test_no_negative_forecasts(self):
        data = make_daily_costs(60, base=1.0, trend_per_day=-0.05)
        result = simple_moving_average_forecast(data, horizon_days=30, window_size=30)
        assert all(v >= 0.0 for v in result["forecast"].values())


class TestCalculateMAPE:
    def test_perfect_prediction(self):
        assert calculate_mape([10, 20, 30], [10, 20, 30]) == 0.0

    def test_known_error(self):
        # |10-12|/10 = 20%, |20-18|/20 = 10% -> MAPE 15%
        assert calculate_mape([10.0, 20.0], [12.0, 18.0]) == pytest.approx(15.0)

    def test_length_mismatch_returns_none(self):
        assert calculate_mape([1, 2], [1]) is None

    def test_empty_returns_none(self):
        assert calculate_mape([], []) is None

    def test_zero_actuals_skipped(self):
        # Only the nonzero actual contributes
        mape = calculate_mape([0, 100], [50, 150])
        assert mape == pytest.approx(50.0)


class TestValidateForecastMAPE:
    def test_insufficient_data(self):
        result = validate_forecast_mape(make_daily_costs(40), holdout_days=30, window_size=30)
        assert result["valid"] is False
        assert "mape" in result

    def test_sufficient_data_returns_valid(self):
        data = make_daily_costs(120, base=200.0, trend_per_day=0.1)
        result = validate_forecast_mape(data, holdout_days=30, window_size=30)
        assert result["valid"] is True
        assert result["mape"] is not None
        assert len(result["actual_vs_predicted"]) == 30

    def test_smooth_series_low_mape(self):
        # Nearly flat series should validate well
        start = date(2026, 1, 1)
        data = [{"date": start + timedelta(days=i), "cost": 100.0} for i in range(120)]
        result = validate_forecast_mape(data, holdout_days=30, window_size=30)
        assert result["valid"] is True
        assert result["mape"] < 5.0


class TestGenerateFullForecast:
    def test_full_pipeline_structure(self):
        data = make_daily_costs(120, base=150.0, trend_per_day=0.2)
        result = generate_full_forecast(data, horizon_days=30, holdout_days=30, window_size=30)
        assert set(result.keys()) == {"forecast", "model", "validation", "mape_within_threshold"}
        assert result["model"]["type"] == "SMA_with_trend"
        assert isinstance(result["mape_within_threshold"], bool)

    def test_horizon_respected(self):
        data = make_daily_costs(120)
        result = generate_full_forecast(data, horizon_days=45)
        assert len(result["forecast"]) == 45
