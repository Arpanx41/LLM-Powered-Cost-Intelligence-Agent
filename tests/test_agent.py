"""Tests for Cost Intelligence Agent."""
import statistics
from datetime import date, timedelta
from unittest.mock import MagicMock, patch, AsyncMock

import pytest

from app.agents.cost_agent import CostAgent
from app.agents.state import AgentState


def _make_state(**overrides) -> AgentState:
    defaults = dict(query="Show me EC2 costs", account_id=None, chat_history=[])
    defaults.update(overrides)
    return AgentState(**defaults)


def _fake_daily_costs(n: int = 60, base: float = 100.0) -> list[dict]:
    start = date(2026, 1, 1)
    return [
        {"date": start + timedelta(days=i), "cost": base + (i * 0.5)}
        for i in range(n)
    ]


# ---------------------------------------------------------------------------
# _timeframe_to_range
# ---------------------------------------------------------------------------

class TestTimeframeToRange:
    def test_default_fallback(self):
        agent = CostAgent()
        start, end = agent._timeframe_to_range("unknown")
        assert end == date.today()
        assert (end - start).days == 30

    def test_last_7_days(self):
        agent = CostAgent()
        start, end = agent._timeframe_to_range("last_7_days")
        assert (end - start).days == 7

    def test_this_month(self):
        agent = CostAgent()
        start, end = agent._timeframe_to_range("this_month")
        assert start.day == 1
        assert end == date.today()


# ---------------------------------------------------------------------------
# _detect_anomalies
# ---------------------------------------------------------------------------

class TestDetectAnomalies:
    def test_insufficient_data_returns_empty(self):
        agent = CostAgent()
        assert agent._detect_anomalies(_fake_daily_costs(3)) == []

    def test_no_spike_returns_empty(self):
        # Flat series: no anomaly
        start = date(2026, 1, 1)
        flat = [{"date": start + timedelta(days=i), "cost": 100.0} for i in range(20)]
        agent = CostAgent()
        assert agent._detect_anomalies(flat) == []

    def test_spike_detected(self):
        start = date(2026, 1, 1)
        costs = [{"date": start + timedelta(days=i), "cost": 100.0} for i in range(20)]
        costs[-1]["cost"] = 500.0  # big spike
        agent = CostAgent()
        anomalies = agent._detect_anomalies(costs)
        assert any(a["cost"] == 500.0 for a in anomalies)


# ---------------------------------------------------------------------------
# parse_query
# ---------------------------------------------------------------------------

class TestParseQuery:
    def test_sets_date_range_on_llm_failure(self):
        agent = CostAgent()
        state = _make_state()
        # Force LLM failure
        with patch.object(agent, "_llm_parse", side_effect=Exception("no LLM")):
            state = agent.parse_query(state)
        assert state.date_range is not None
        start, end = state.date_range
        assert (end - start).days == 30


# ---------------------------------------------------------------------------
# generate_recommendations
# ---------------------------------------------------------------------------

class TestGenerateRecommendations:
    @patch("app.agents.cost_agent.session_scope")
    @patch("app.agents.cost_agent.get_accounts")
    @patch("app.agents.cost_agent.create_recommendation")
    def test_ec2_rec_generated(self, mock_create, mock_accounts, mock_scope):
        mock_accounts.return_value = [MagicMock(account_id="111")]
        ctx = MagicMock()
        ctx.__enter__ = MagicMock(return_value=MagicMock())
        ctx.__exit__ = MagicMock(return_value=False)
        mock_scope.return_value = ctx

        agent = CostAgent()
        state = _make_state()
        state.top_services = [
            {"service": "Amazon Elastic Compute Cloud - Compute", "cost": 120.0, "percentage": 40.0}
        ]
        state.optimization_patterns = []

        with patch.object(agent, "_llm_recommendations", return_value=[]):
            state = agent.generate_recommendations(state)

        types = [r["type"] for r in state.recommendations]
        assert "reserved_instances" in types


# ---------------------------------------------------------------------------
# forecast_costs
# ---------------------------------------------------------------------------

class TestForecastCosts:
    def test_no_data_returns_error(self):
        agent = CostAgent()
        state = _make_state()
        state.daily_costs = []
        state = agent.forecast_costs(state)
        assert "error" in state.forecast

    @patch("app.agents.cost_agent.generate_full_forecast")
    def test_calls_forecast(self, mock_gen):
        mock_gen.return_value = {"forecast": {"2026-04-01": 100.0}, "validation": {"mape": 8.0}}
        agent = CostAgent()
        state = _make_state()
        state.daily_costs = _fake_daily_costs(90)
        state = agent.forecast_costs(state)
        mock_gen.assert_called_once()
        assert state.forecast["2026-04-01"] == 100.0


# ---------------------------------------------------------------------------
# build_workflow
# ---------------------------------------------------------------------------

class TestBuildWorkflow:
    def test_returns_compiled_or_none(self):
        from app.agents.cost_agent import build_workflow
        result = build_workflow()
        # Should either return compiled graph or None (if langgraph missing)
        assert result is None or hasattr(result, "invoke")
