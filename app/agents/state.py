"""LangGraph state definition for Cost Intelligence Agent."""
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field
from datetime import date


@dataclass
class AgentState:
    """State passed through LangGraph workflow."""
    # Input
    query: str = ""
    account_id: Optional[str] = None
    date_range: Optional[tuple[date, date]] = None

    # Retrieved data
    billing_summary: Dict[str, Any] = field(default_factory=dict)
    daily_costs: List[Dict[str, Any]] = field(default_factory=list)
    optimization_patterns: List[Dict[str, Any]] = field(default_factory=list)

    # Analysis results
    anomalies: List[Dict[str, Any]] = field(default_factory=list)
    top_services: List[Dict[str, Any]] = field(default_factory=list)

    # Recommendations
    recommendations: List[Dict[str, Any]] = field(default_factory=list)

    # Forecast
    forecast: Dict[str, Any] = field(default_factory=dict)
    forecast_validation: Dict[str, Any] = field(default_factory=dict)

    # Output
    response: str = ""
    errors: List[str] = field(default_factory=list)

    # Metadata
    chat_history: List[str] = field(default_factory=list)
    step: str = "start"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "query": self.query,
            "account_id": self.account_id,
            "date_range": self.date_range,
            "billing_summary": self.billing_summary,
            "daily_costs": self.daily_costs,
            "optimization_patterns": self.optimization_patterns,
            "anomalies": self.anomalies,
            "top_services": self.top_services,
            "recommendations": self.recommendations,
            "forecast": self.forecast,
            "forecast_validation": self.forecast_validation,
            "response": self.response,
            "errors": self.errors,
            "chat_history": self.chat_history,
            "step": self.step,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AgentState":
        state = cls()
        for key, value in data.items():
            if hasattr(state, key):
                setattr(state, key, value)
        return state