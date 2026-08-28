"""Simple local forecasting with MAPE validation."""
from datetime import date, timedelta
from decimal import Decimal
from typing import List, Dict, Any, Optional, Tuple
import statistics

from app.config import settings


def simple_moving_average_forecast(
    daily_costs: List[Dict[str, Any]],
    horizon_days: int = 90,
    window_size: int = 30,
) -> Dict[str, Any]:
    """
    Generate forecast using simple moving average with trend adjustment.

    Args:
        daily_costs: List of {"date": date, "cost": float} sorted by date
        horizon_days: Number of days to forecast
        window_size: Moving average window

    Returns:
        Dict with forecast, model info, and validation metrics
    """
    if len(daily_costs) < window_size + 1:
        return {
            "error": f"Insufficient data: need at least {window_size + 1} days, got {len(daily_costs)}",
            "forecast": {},
            "model_type": "SMA",
            "mape": None,
        }

    # Sort by date
    sorted_costs = sorted(daily_costs, key=lambda x: x["date"])
    dates = [d["date"] for d in sorted_costs]
    costs = [d["cost"] for d in sorted_costs]

    # Calculate moving averages
    moving_avgs = []
    for i in range(window_size, len(costs)):
        window = costs[i - window_size:i]
        moving_avgs.append(statistics.mean(window))

    # Simple trend: slope of last few moving averages
    if len(moving_avgs) >= 5:
        recent = moving_avgs[-5:]
        trend = (recent[-1] - recent[0]) / len(recent)
    else:
        trend = 0.0

    # Last known moving average as base
    last_ma = moving_avgs[-1] if moving_avgs else statistics.mean(costs[-window_size:])

    # Generate forecast
    last_date = dates[-1]
    forecast = {}
    for day in range(1, horizon_days + 1):
        forecast_date = last_date + timedelta(days=day)
        # Apply trend
        forecast_value = last_ma + (trend * day)
        # Floor at 0
        forecast_value = max(0.0, forecast_value)
        forecast[forecast_date.isoformat()] = round(forecast_value, 2)

    return {
        "forecast": forecast,
        "model_type": "SMA_with_trend",
        "window_size": window_size,
        "trend_per_day": round(trend, 4),
        "last_known_ma": round(last_ma, 2),
    }


def calculate_mape(actual: List[float], predicted: List[float]) -> Optional[float]:
    """Calculate Mean Absolute Percentage Error."""
    if len(actual) != len(predicted) or not actual:
        return None

    errors = []
    for a, p in zip(actual, predicted):
        if a != 0:
            errors.append(abs((a - p) / a))

    if not errors:
        return 0.0

    return (sum(errors) / len(errors)) * 100


def validate_forecast_mape(
    daily_costs: List[Dict[str, Any]],
    horizon_days: int = 90,
    holdout_days: int = 30,
    window_size: int = 30,
) -> Dict[str, Any]:
    """
    Validate forecast by training on earlier data and testing on holdout period.

    Args:
        daily_costs: Full historical data
        horizon_days: Forecast horizon for final model
        holdout_days: Days to hold out for validation
        window_size: SMA window

    Returns:
        Validation results including MAPE
    """
    sorted_costs = sorted(daily_costs, key=lambda x: x["date"])

    if len(sorted_costs) < window_size + holdout_days + 1:
        return {
            "valid": False,
            "error": f"Need at least {window_size + holdout_days + 1} days of data",
            "mape": None,
        }

    # Split: train on all but last holdout_days, validate on holdout
    train_data = sorted_costs[:-holdout_days]
    test_data = sorted_costs[-holdout_days:]

    # Train forecast on train_data
    train_result = simple_moving_average_forecast(
        train_data,
        horizon_days=holdout_days,
        window_size=window_size,
    )

    if "error" in train_result:
        return {"valid": False, "error": train_result["error"], "mape": None}

    # Compare forecast with actual holdout
    forecast = train_result["forecast"]
    actual_values = [d["cost"] for d in test_data]
    predicted_values = []

    for i, d in enumerate(test_data):
        pred = forecast.get(d["date"].isoformat())
        if pred is not None:
            predicted_values.append(pred)

    if len(predicted_values) != len(actual_values):
        return {"valid": False, "error": "Forecast/actual length mismatch", "mape": None}

    mape = calculate_mape(actual_values, predicted_values)

    return {
        "valid": True,
        "mape": round(mape, 2) if mape is not None else None,
        "holdout_days": holdout_days,
        "actual_vs_predicted": [
            {"date": d["date"].isoformat(), "actual": a, "predicted": p}
            for d, a, p in zip(test_data, actual_values, predicted_values)
        ],
    }


def generate_full_forecast(
    daily_costs: List[Dict[str, Any]],
    horizon_days: int = 90,
    holdout_days: int = 30,
    window_size: int = 30,
) -> Dict[str, Any]:
    """Generate forecast with validation."""
    # Validate first
    validation = validate_forecast_mape(
        daily_costs, horizon_days, holdout_days, window_size
    )

    # Generate final forecast on all data
    forecast_result = simple_moving_average_forecast(
        daily_costs, horizon_days, window_size
    )

    return {
        "forecast": forecast_result.get("forecast", {}),
        "model": {
            "type": forecast_result.get("model_type"),
            "window_size": forecast_result.get("window_size"),
            "trend_per_day": forecast_result.get("trend_per_day"),
        },
        "validation": validation,
        "mape_within_threshold": (
            validation.get("mape") is not None
            and validation["mape"] <= settings.mape_threshold
        ),
    }