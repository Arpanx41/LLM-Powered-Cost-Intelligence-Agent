"""Pydantic models for request/response validation."""
from typing import Any, List, Optional
from pydantic import BaseModel, Field, ConfigDict
from datetime import date


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str = "1.0.0"


# Billing endpoints
class BillingSummaryResponse(BaseModel):
    account_id: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    services: List[dict]
    total_cost: float


class AccountResponse(BaseModel):
    account_id: str
    account_name: str
    environment: str
    provider: str


class AccountsListResponse(BaseModel):
    accounts: List[AccountResponse]
    total: int


class IngestRequest(BaseModel):
    file_path: Optional[str] = None
    account_id: Optional[str] = None


class IngestResponse(BaseModel):
    success: bool
    records_ingested: int
    message: str


# Chat endpoints
class ChatRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    account_id: Optional[str] = None
    chat_history: List[str] = Field(default_factory=list)


class ChatResponse(BaseModel):
    response: str
    chat_history: List[str]
    recommendations: List[dict] = Field(default_factory=list)
    forecast: dict = Field(default_factory=dict)
    forecast_validation: dict = Field(default_factory=dict)
    billing_summary: dict = Field(default_factory=dict)
    top_services: List[dict] = Field(default_factory=list)
    anomalies: List[dict] = Field(default_factory=list)


# Recommendations
class RecommendationResponse(BaseModel):
    id: int
    account_id: str
    service: str
    recommendation_type: str
    estimated_monthly_savings: float
    description: str
    details: Optional[str] = None
    confidence: Optional[str] = None
    status: str
    created_at: str


class RecommendationsListResponse(BaseModel):
    recommendations: List[RecommendationResponse]
    total: int
    summary_by_type: dict


# Forecast
class ForecastResponse(BaseModel):
    account_id: str
    horizon_days: int
    forecast: dict
    model: dict
    validation: dict
    mape_within_threshold: bool