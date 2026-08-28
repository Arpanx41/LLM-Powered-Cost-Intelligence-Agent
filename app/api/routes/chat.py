"""Chat API routes for Cost Intelligence Agent."""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.agents.cost_agent import run_agent_sequential
from app.db.crud import get_recommendations, get_recommendations_summary
from app.db.session import get_db
from app.schemas import ChatRequest, ChatResponse, RecommendationsListResponse, RecommendationResponse

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("", response_model=ChatResponse)
async def chat_with_agent(
    request: ChatRequest,
    db: Session = Depends(get_db),
):
    """Main chat endpoint for cost intelligence queries."""
    try:
        result = await run_agent_sequential(
            query=request.query,
            account_id=request.account_id,
            chat_history=request.chat_history,
        )
        return ChatResponse(**result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Agent error: {e}")


@router.get("/recommendations", response_model=RecommendationsListResponse)
async def list_recommendations(
    account_id: Optional[str] = None,
    status: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Get stored recommendations."""
    recs = get_recommendations(db, account_id, status)
    summary = get_recommendations_summary(db, account_id) if account_id else {}

    return RecommendationsListResponse(
        recommendations=[
            RecommendationResponse(
                id=r.id,
                account_id=r.account_id,
                service=r.service,
                recommendation_type=r.recommendation_type,
                estimated_monthly_savings=float(r.estimated_monthly_savings),
                description=r.description,
                details=r.details,
                confidence=r.confidence,
                status=r.status,
                created_at=r.created_at.isoformat(),
            )
            for r in recs
        ],
        total=len(recs),
        summary_by_type=summary,
    )


@router.get("/recommendations/summary")
async def recommendations_summary(
    account_id: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Get recommendations summary by type."""
    return get_recommendations_summary(db, account_id) if account_id else {}


@router.get("/forecast/{account_id}")
async def get_forecast(
    account_id: str,
    horizon_days: int = 90,
    db: Session = Depends(get_db),
):
    """Get cost forecast for an account."""
    from app.db.crud import get_daily_costs
    from app.services.forecasting import generate_full_forecast
    from datetime import date, timedelta

    end_date = date.today()
    start_date = end_date - timedelta(days=180)  # Need history for forecast

    daily_costs = get_daily_costs(db, account_id, start_date, end_date)

    if not daily_costs:
        raise HTTPException(status_code=404, detail="No billing data for this account")

    result = generate_full_forecast(
        daily_costs,
        horizon_days=horizon_days,
        holdout_days=30,
    )

    return {
        "account_id": account_id,
        "horizon_days": horizon_days,
        "forecast": result.get("forecast", {}),
        "model": result.get("model", {}),
        "validation": result.get("validation", {}),
        "mape_within_threshold": result.get("mape_within_threshold", False),
    }