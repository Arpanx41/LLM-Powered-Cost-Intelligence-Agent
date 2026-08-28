"""Billing data API routes."""
from datetime import date, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.config import settings
from app.db.crud import (
    get_account,
    get_accounts,
    get_billing_records,
    get_cost_summary,
    get_daily_costs,
    get_date_range,
    refresh_daily_aggregates,
    upsert_account,
)
from app.db.models import Account, BillingRecord
from app.db.session import get_db
from app.schemas import (
    AccountsListResponse,
    AccountResponse,
    BillingSummaryResponse,
    IngestRequest,
    IngestResponse,
)
from app.services.billing_ingestion import ingest_billing_csv

router = APIRouter(prefix="/billing", tags=["billing"])


@router.get("/accounts", response_model=AccountsListResponse)
async def list_accounts(db: Session = Depends(get_db)):
    """List all billing accounts."""
    accounts = get_accounts(db)
    return AccountsListResponse(
        accounts=[
            AccountResponse(
                account_id=a.account_id,
                account_name=a.account_name,
                environment=a.environment,
                provider=a.provider,
            )
            for a in accounts
        ],
        total=len(accounts),
    )


@router.get("/summary", response_model=BillingSummaryResponse)
async def get_summary(
    account_id: Optional[str] = Query(None, description="Filter by account"),
    start_date: Optional[date] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[date] = Query(None, description="End date (YYYY-MM-DD)"),
    db: Session = Depends(get_db),
):
    """Get cost summary by service for a date range."""
    if not start_date:
        end = date.today()
        start_date = end - timedelta(days=30)
    if not end_date:
        end_date = date.today()

    summary = get_cost_summary(db, account_id, start_date, end_date)
    total = sum(s["total_cost"] for s in summary)

    return BillingSummaryResponse(
        account_id=account_id,
        start_date=start_date,
        end_date=end_date,
        services=summary,
        total_cost=total,
    )


@router.get("/daily-costs")
async def get_daily(
    account_id: Optional[str] = Query(None),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    db: Session = Depends(get_db),
):
    """Get daily cost totals for forecasting."""
    if not start_date:
        end = date.today()
        start_date = end - timedelta(days=90)
    if not end_date:
        end_date = date.today()

    daily = get_daily_costs(db, account_id, start_date, end_date)
    return {
        "account_id": account_id,
        "start_date": start_date,
        "end_date": end_date,
        "daily_costs": daily,
    }


@router.get("/records")
async def list_records(
    account_id: Optional[str] = Query(None),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    service: Optional[str] = Query(None),
    limit: int = Query(100, le=1000),
    db: Session = Depends(get_db),
):
    """List raw billing records with filters."""
    records = get_billing_records(db, account_id, start_date, end_date, service, limit)
    return {
        "records": [
            {
                "id": r.id,
                "account_id": r.account_id,
                "usage_date": r.usage_date.isoformat(),
                "service": r.service,
                "usage_type": r.usage_type,
                "operation": r.operation,
                "region": r.region,
                "usage_quantity": float(r.usage_quantity),
                "unit": r.unit,
                "blended_cost": float(r.blended_cost),
                "currency": r.currency,
            }
            for r in records
        ],
        "total": len(records),
    }


@router.post("/generate-sample-data", response_model=IngestResponse)
async def generate_sample_data(
    request: IngestRequest,
    db: Session = Depends(get_db),
):
    """Generate synthetic AWS billing data and ingest it."""
    file_path = request.file_path or settings.sample_data_path

    # Generate if not exists
    import os
    if not os.path.exists(file_path):
        from scripts.generate_sample_billing_data import generate_aws_billing_data
        generate_aws_billing_data(output_path=file_path)

    # Ingest
    try:
        count = ingest_billing_csv(file_path, db, request.account_id)
        refresh_daily_aggregates(db, request.account_id)
        return IngestResponse(
            success=True,
            records_ingested=count,
            message=f"Ingested {count} billing records from {file_path} and refreshed aggregates",
        )
    except Exception as e:
        return IngestResponse(
            success=False,
            records_ingested=0,
            message=f"Ingestion failed: {e}",
        )


@router.post("/ingest", response_model=IngestResponse)
async def ingest_billing(
    request: IngestRequest,
    db: Session = Depends(get_db),
):
    """Ingest billing data from CSV file."""
    file_path = request.file_path or settings.sample_data_path

    import os
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail=f"File not found: {file_path}")

    try:
        count = ingest_billing_csv(file_path, db, request.account_id)
        # Refresh aggregates
        refresh_daily_aggregates(db, request.account_id)
        return IngestResponse(
            success=True,
            records_ingested=count,
            message=f"Ingested {count} billing records and refreshed aggregates",
        )
    except Exception as e:
        return IngestResponse(
            success=False,
            records_ingested=0,
            message=f"Ingestion failed: {e}",
        )


@router.post("/refresh-aggregates")
async def refresh_aggregates(
    account_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """Refresh daily cost aggregates."""
    count = refresh_daily_aggregates(db, account_id)
    return {"message": f"Refreshed {count} daily aggregates", "account_id": account_id}