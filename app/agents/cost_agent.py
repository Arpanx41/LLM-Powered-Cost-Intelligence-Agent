"""LangGraph workflow for Cost Intelligence Agent."""
import json
import logging
import re
import statistics
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

import httpx

from app.agents.state import AgentState
from app.config import settings
from app.db.crud import (
    get_account,
    get_accounts,
    get_cost_summary,
    get_daily_costs,
    get_date_range,
    create_recommendation,
    get_recommendations,
)
from app.db.session import session_scope
from app.rag.patterns import get_patterns_by_service
from app.rag.retriever import get_retriever
from app.services.embeddings import get_embeddings
from app.services.forecasting import generate_full_forecast

logger = logging.getLogger(__name__)

# LLM prompt templates
PARSE_QUERY_PROMPT = """Extract structured information from the user query about cloud costs.

Query: "{query}"

Extract and return ONLY a JSON object with these fields (null if not mentioned):
- account_id: specific account ID mentioned (e.g., "123456789012")
- environment: "dev", "staging", "prod", or "production"
- service: specific AWS service name mentioned
- timeframe: "last_7_days", "last_30_days", "last_90_days", "this_month", "last_month", "all"
- intent: "summary", "breakdown", "forecast", "recommendations", "anomalies", "chat"

Example: {{"account_id": null, "environment": "prod", "service": "EC2", "timeframe": "last_30_days", "intent": "recommendations"}}"""

ANALYZE_COSTS_PROMPT = """Analyze the following cost data and identify key insights.

Billing Summary (by service):
{billing_summary}

Daily Costs (last 30 days):
{daily_costs}

Top 5 services by cost:
{top_services}

Identify:
1. Top 3 cost-driving services
2. Any cost anomalies (sudden spikes > 2x average)
3. Services with high On-Demand spend (potential for Reserved Instances)
4. Right-sizing opportunities (consistent low utilization patterns)

Return ONLY a JSON object:
{{
  "top_services": [{{"service": "...", "cost": ..., "percentage": ...}}],
  "anomalies": [{{"service": "...", "date": "...", "cost": ..., "expected": ..., "description": "..."}}],
  "high_ondemand_services": [...],
  "rightsizing_candidates": [...]
}}"""

GENERATE_RECOMMENDATIONS_PROMPT = """Generate specific cost optimization recommendations based on analysis and best practices.

Cost Analysis:
{analysis}

Retrieved Optimization Patterns:
{patterns}

Account: {account_id}
Environment: {environment}

Generate 3-5 specific, actionable recommendations. For each include:
- type: right_sizing | reserved_instances | savings_plans | storage_lifecycle | anomaly
- service: affected service
- estimated_monthly_savings_usd: number
- description: clear action item
- details: specific steps (JSON string)
- confidence: high | medium | low

Return ONLY a JSON array of recommendations."""

GENERATE_RESPONSE_PROMPT = """You are a cloud cost optimization assistant. Provide a clear, concise response to the user.

User Query: {query}
Account: {account_id}
Environment: {environment}

Billing Summary:
{billing_summary}

Key Findings:
- Top Services: {top_services}
- Anomalies: {anomalies}
- Recommendations: {recommendations}
- Forecast: {forecast}
- Forecast MAPE: {mape}

Provide a helpful response summarizing the analysis, recommendations, and forecast.
Include specific numbers and actionable next steps.
Keep it concise but informative."""


class CostAgent:
    """LangGraph-based cost intelligence agent."""

    def __init__(self):
        self.embeddings = get_embeddings()
        self.retriever = get_retriever()

    # --- Node Functions ---

    def parse_query(self, state: AgentState) -> AgentState:
        """Parse user query to extract intent and parameters."""
        state.step = "parse_query"

        # Use LLM to parse (fallback to keyword matching)
        try:
            parsed = self._llm_parse(state.query)
            state.account_id = parsed.get("account_id") or state.account_id
            state.date_range = self._timeframe_to_range(parsed.get("timeframe", "last_30_days"))
        except Exception as e:
            logger.warning("LLM parse failed, using defaults: %s", e)
            state.date_range = self._timeframe_to_range("last_30_days")

        return state

    def retrieve_billing_data(self, state: AgentState) -> AgentState:
        """Query PostgreSQL for billing data."""
        state.step = "retrieve_billing_data"

        with session_scope() as db:
            # Determine account
            account_id = state.account_id
            if not account_id:
                accounts = get_accounts(db)
                if accounts:
                    account_id = accounts[0].account_id

            start_date, end_date = state.date_range or (None, None)

            # Get cost summary
            summary = get_cost_summary(db, account_id, start_date, end_date)
            state.billing_summary = {s["service"]: s["total_cost"] for s in summary}

            # Get daily costs for forecasting
            daily = get_daily_costs(db, account_id, start_date, end_date)
            state.daily_costs = daily

            # Get date range
            min_d, max_d = get_date_range(db, account_id)
            if min_d and max_d:
                state.date_range = (min_d, max_d)

        return state

    def retrieve_optimization_patterns(self, state: AgentState) -> AgentState:
        """Retrieve relevant optimization patterns from ChromaDB."""
        state.step = "retrieve_optimization_patterns"

        # Build query from top services
        top_services = list(state.billing_summary.keys())[:5]
        query_text = f"Cost optimization for {', '.join(top_services)}"

        all_patterns = []
        try:
            query_embedding = self.embeddings.embed_query(query_text)
            for service in top_services:
                patterns = self.retriever.retrieve(
                    query_embedding, top_k=3, service_filter=service
                )
                all_patterns.extend(patterns)
        except Exception as e:
            logger.warning("Pattern retrieval failed, using static patterns: %s", e)
            for service in top_services:
                all_patterns.extend(
                    {
                        "content": pattern["content"],
                        "metadata": {
                            "id": pattern["id"],
                            "category": pattern["category"],
                            "services": ",".join(pattern["services"]),
                        },
                        "distance": None,
                    }
                    for pattern in get_patterns_by_service(service)
                )

        # Deduplicate by pattern ID
        seen = set()
        unique_patterns = []
        for p in all_patterns:
            pid = p["metadata"].get("id")
            if pid and pid not in seen:
                seen.add(pid)
                unique_patterns.append(p)

        state.optimization_patterns = unique_patterns[:10]
        return state

    def analyze_costs(self, state: AgentState) -> AgentState:
        """Analyze costs for anomalies and opportunities."""
        state.step = "analyze_costs"

        # Compute top services
        sorted_services = sorted(
            state.billing_summary.items(), key=lambda x: x[1], reverse=True
        )
        total = sum(state.billing_summary.values()) or 1
        top_services = [
            {"service": s, "cost": c, "percentage": round(c / total * 100, 1)}
            for s, c in sorted_services[:5]
        ]
        state.top_services = top_services

        # Simple anomaly detection on daily costs
        anomalies = self._detect_anomalies(state.daily_costs)
        state.anomalies = anomalies

        # Use LLM for deeper analysis if available
        try:
            llm_analysis = self._llm_analyze(state)
            state.anomalies.extend(llm_analysis.get("anomalies", []))
            state.top_services = llm_analysis.get("top_services", state.top_services)
        except Exception as e:
            logger.warning("LLM analysis failed: %s", e)

        return state

    def generate_recommendations(self, state: AgentState) -> AgentState:
        """Generate specific cost optimization recommendations."""
        state.step = "generate_recommendations"

        recommendations = []

        # Rule-based recommendations
        for svc in state.top_services:
            service_name = svc["service"]
            cost = svc["cost"]
            pct = svc["percentage"]

            # High On-Demand EC2 → Reserved Instances
            if "Elastic Compute Cloud" in service_name and cost > 50:
                savings = round(cost * 0.4, 2)  # ~40% savings
                recommendations.append({
                    "type": "reserved_instances",
                    "service": service_name,
                    "estimated_monthly_savings_usd": savings,
                    "description": f"Purchase 1-year Reserved Instances for {service_name} (steady workload)",
                    "details": json.dumps({"term": "1yr", "payment_option": "Partial Upfront"}),
                    "confidence": "high",
                })

            # High S3 → Lifecycle policies
            if "Simple Storage Service" in service_name and cost > 20:
                savings = round(cost * 0.3, 2)
                recommendations.append({
                    "type": "storage_lifecycle",
                    "service": service_name,
                    "estimated_monthly_savings_usd": savings,
                    "description": f"Enable S3 Intelligent-Tiering and lifecycle rules for {service_name}",
                    "details": json.dumps({"transition_days": [30, 90, 365], "tiers": ["IA", "Glacier", "Deep Archive"]}),
                    "confidence": "high",
                })

            # RDS → Right-sizing
            if "Relational Database Service" in service_name and cost > 30:
                savings = round(cost * 0.25, 2)
                recommendations.append({
                    "type": "right_sizing",
                    "service": service_name,
                    "estimated_monthly_savings_usd": savings,
                    "description": f"Review {service_name} instance class and storage type (gp3)",
                    "details": json.dumps({"action": "downsize_instance", "storage_type": "gp3"}),
                    "confidence": "medium",
                })

        # LLM-enhanced recommendations using patterns
        try:
            llm_recs = self._llm_recommendations(state)
            recommendations.extend(llm_recs)
        except Exception as e:
            logger.warning("LLM recommendations failed: %s", e)

        # Save to database
        with session_scope() as db:
            account_id = state.account_id or (get_accounts(db)[0].account_id if get_accounts(db) else None)
            if account_id:
                for rec in recommendations:
                    create_recommendation(
                        db,
                        account_id=account_id,
                        service=rec["service"],
                        recommendation_type=rec["type"],
                        estimated_monthly_savings=rec["estimated_monthly_savings_usd"],
                        description=rec["description"],
                        details=rec["details"],
                        confidence=rec["confidence"],
                    )

        state.recommendations = recommendations
        return state

    def forecast_costs(self, state: AgentState) -> AgentState:
        """Generate cost forecast with MAPE validation."""
        state.step = "forecast_costs"

        if not state.daily_costs:
            state.forecast = {"error": "No daily cost data available"}
            return state

        result = generate_full_forecast(
            state.daily_costs,
            horizon_days=settings.forecast_horizon_days,
            holdout_days=settings.forecast_holdout_days,
        )
        state.forecast = result.get("forecast", {})
        state.forecast_validation = result.get("validation", {})
        return state

    def generate_response(self, state: AgentState) -> AgentState:
        """Generate final natural language response."""
        state.step = "generate_response"

        # Build summary
        top_svc_str = ", ".join(
            f"{s['service']} (${s['cost']:.2f}, {s['percentage']}%)" for s in state.top_services[:3]
        )
        anomalies_str = "; ".join(
            f"{a['service']} on {a['date']}: ${a['cost']:.2f} (expected ~${a['expected']:.2f})"
            for a in state.anomalies[:3]
        )
        recs_str = "; ".join(
            f"{r['type']} on {r['service']}: save ~${r['estimated_monthly_savings_usd']:.2f}/mo"
            for r in state.recommendations[:3]
        )
        forecast_str = ""
        if state.forecast:
            total_forecast = sum(state.forecast.values())
            forecast_str = f"${total_forecast:.2f} over next {settings.forecast_horizon_days} days"

        mape = state.forecast_validation.get("mape")
        mape_str = f"{mape}%" if mape else "N/A"

        try:
            # Try LLM response
            prompt = GENERATE_RESPONSE_PROMPT.format(
                query=state.query,
                account_id=state.account_id or "all",
                environment="production",
                billing_summary=json.dumps(state.billing_summary, indent=2),
                top_services=top_svc_str,
                anomalies=anomalies_str or "None detected",
                recommendations=recs_str or "None generated",
                forecast=forecast_str,
                mape=mape_str,
            )
            response = self._llm_generate(prompt)
        except Exception:
            # Fallback template response
            response = self._template_response(state, top_svc_str, anomalies_str, recs_str, forecast_str, mape_str)

        state.response = response
        state.chat_history.append(f"User: {state.query}")
        state.chat_history.append(f"Assistant: {response}")
        return state

    # --- Helper Methods ---

    def _timeframe_to_range(self, timeframe: str) -> tuple:
        end = date.today()
        if timeframe == "last_7_days":
            return (end - timedelta(days=7), end)
        elif timeframe == "last_30_days":
            return (end - timedelta(days=30), end)
        elif timeframe == "last_90_days":
            return (end - timedelta(days=90), end)
        elif timeframe == "this_month":
            return (end.replace(day=1), end)
        elif timeframe == "last_month":
            first_this = end.replace(day=1)
            last_month_end = first_this - timedelta(days=1)
            return (last_month_end.replace(day=1), last_month_end)
        return (end - timedelta(days=30), end)

    def _detect_anomalies(self, daily_costs: List[Dict]) -> List[Dict]:
        """Simple statistical anomaly detection."""
        if len(daily_costs) < 7:
            return []

        costs = [d["cost"] for d in daily_costs]
        mean_cost = statistics.mean(costs)
        stdev = statistics.stdev(costs) if len(costs) > 1 else 0
        threshold = mean_cost + 2 * stdev

        anomalies = []
        for d in daily_costs[-14:]:  # Check last 2 weeks
            if d["cost"] > threshold:
                anomalies.append({
                    "service": "aggregate",
                    "date": d["date"].isoformat() if hasattr(d["date"], "isoformat") else str(d["date"]),
                    "cost": d["cost"],
                    "expected": round(mean_cost, 2),
                    "description": f"Cost spike: {d['cost']:.2f} vs expected ~{mean_cost:.2f}",
                })
        return anomalies

    def _llm_parse(self, query: str) -> Dict:
        """Use Ollama to parse query."""
        prompt = PARSE_QUERY_PROMPT.format(query=query)
        return self._llm_json(prompt)

    def _llm_analyze(self, state: AgentState) -> Dict:
        """Use LLM for cost analysis."""
        prompt = ANALYZE_COSTS_PROMPT.format(
            billing_summary=json.dumps(state.billing_summary, indent=2),
            daily_costs=json.dumps(state.daily_costs[-30:], indent=2, default=str),
            top_services=json.dumps(state.top_services, indent=2),
        )
        return self._llm_json(prompt)

    def _llm_recommendations(self, state: AgentState) -> List[Dict]:
        """Use LLM for recommendations."""
        patterns_text = "\n\n".join(
            f"Pattern: {p['metadata'].get('id')}\n{p['content'][:500]}"
            for p in state.optimization_patterns
        )
        prompt = GENERATE_RECOMMENDATIONS_PROMPT.format(
            analysis=json.dumps({
                "top_services": state.top_services,
                "anomalies": state.anomalies,
            }, indent=2),
            patterns=patterns_text,
            account_id=state.account_id or "all",
            environment="production",
        )
        result = self._llm_json(prompt)
        return result if isinstance(result, list) else []

    def _llm_generate(self, prompt: str) -> str:
        """Call Ollama generate endpoint."""
        payload = {
            "model": settings.ollama_chat_model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.2},
        }
        resp = httpx.post(
            f"{settings.ollama_base_url}/api/generate",
            json=payload,
            timeout=settings.ollama_timeout,
        )
        resp.raise_for_status()
        return resp.json().get("response", "").strip()

    def _llm_json(self, prompt: str) -> Any:
        """Call Ollama and parse JSON response."""
        response = self._llm_generate(prompt)
        # Extract JSON from response
        match = re.search(r"\{.*\}|\[.*\]", response, re.DOTALL)
        if match:
            return json.loads(match.group())
        return {}

    def _template_response(
        self, state: AgentState, top_svc: str, anomalies: str, recs: str, forecast: str, mape: str
    ) -> str:
        """Template-based response when LLM unavailable."""
        lines = [
            f"## Cost Analysis for {state.account_id or 'all accounts'}",
            f"**Query**: {state.query}",
            "",
            f"### Top Cost Drivers: {top_svc or 'No data'}",
        ]
        if anomalies:
            lines.append(f"\n### Anomalies Detected: {anomalies}")
        if recs:
            lines.append(f"\n### Recommendations: {recs}")
        if forecast:
            lines.append(f"\n### 90-Day Forecast: {forecast} (MAPE: {mape})")
        lines.append("\n*Run with Ollama for enhanced AI-powered insights.*")
        return "\n".join(lines)


def build_workflow() -> Any:
    """Build LangGraph workflow."""
    try:
        from langgraph.graph import StateGraph, END

        workflow = StateGraph(AgentState)

        # Add nodes
        agent = CostAgent()
        workflow.add_node("parse_query", agent.parse_query)
        workflow.add_node("retrieve_billing_data", agent.retrieve_billing_data)
        workflow.add_node("retrieve_optimization_patterns", agent.retrieve_optimization_patterns)
        workflow.add_node("analyze_costs", agent.analyze_costs)
        workflow.add_node("generate_recommendations", agent.generate_recommendations)
        workflow.add_node("forecast_costs", agent.forecast_costs)
        workflow.add_node("generate_response", agent.generate_response)

        # Add edges
        workflow.set_entry_point("parse_query")
        workflow.add_edge("parse_query", "retrieve_billing_data")
        workflow.add_edge("retrieve_billing_data", "retrieve_optimization_patterns")
        workflow.add_edge("retrieve_optimization_patterns", "analyze_costs")
        workflow.add_edge("analyze_costs", "generate_recommendations")
        workflow.add_edge("generate_recommendations", "forecast_costs")
        workflow.add_edge("forecast_costs", "generate_response")
        workflow.add_edge("generate_response", END)

        return workflow.compile()
    except ImportError:
        logger.warning("LangGraph not installed; using sequential execution")
        return None


# Sequential fallback for when LangGraph isn't available
async def run_agent_sequential(query: str, account_id: str = None, chat_history: List[str] = None) -> Dict[str, Any]:
    """Run agent nodes sequentially without LangGraph."""
    state = AgentState(query=query, account_id=account_id, chat_history=chat_history or [])
    agent = CostAgent()

    state = agent.parse_query(state)
    state = agent.retrieve_billing_data(state)
    state = agent.retrieve_optimization_patterns(state)
    state = agent.analyze_costs(state)
    state = agent.generate_recommendations(state)
    state = agent.forecast_costs(state)
    state = agent.generate_response(state)

    return {
        "response": state.response,
        "chat_history": state.chat_history,
        "recommendations": state.recommendations,
        "forecast": state.forecast,
        "forecast_validation": state.forecast_validation,
        "billing_summary": state.billing_summary,
        "top_services": state.top_services,
        "anomalies": state.anomalies,
    }