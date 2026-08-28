"""Database CRUD operations."""
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import List, Optional, Tuple

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Account, BillingRecord, DailyCostAggregate, Recommendation


# --- Accounts ---

def get_accounts(db: Session) -> List[Account]:
    return db.execute(select(Account)).scalars().all()


def get_account(db: Session, account_id: str) -> Optional[Account]:
    return db.get(Account, account_id)


def create_account(
    db: Session,
    account_id: str,
    account_name: str,
    environment: str,
    provider: str = "AWS",
) -> Account:
    account = Account(
        account_id=account_id,
        account_name=account_name,
        environment=environment,
        provider=provider,
    )
    db.add(account)
    db.flush()
    return account


def upsert_account(
    db: Session,
    account_id: str,
    account_name: str,
    environment: str,
    provider: str = "AWS",
) -> Account:
    account = db.get(Account, account_id)
    if account:
        account.account_name = account_name
        account.environment = environment
        account.provider = provider
    else:
        account = create_account(db, account_id, account_name, environment, provider)
    return account


# --- Billing Records ---

def bulk_insert_billing_records(db: Session, records: List[BillingRecord]) -> int:
    db.bulk_save_objects(records)
    db.flush()
    return len(records)


def get_billing_records(
    db: Session,
    account_id: Optional[str] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    service: Optional[str] = None,
    limit: int = 1000,
) -> List[BillingRecord]:
    stmt = select(BillingRecord)
    if account_id:
        stmt = stmt.where(BillingRecord.account_id == account_id)
    if start_date:
        stmt = stmt.where(BillingRecord.usage_date >= start_date)
    if end_date:
        stmt = stmt.where(BillingRecord.usage_date <= end_date)
    if service:
        stmt = stmt.where(BillingRecord.service == service)
    stmt = stmt.order_by(BillingRecord.usage_date.desc()).limit(limit)
    return db.execute(stmt).scalars().all()


def get_cost_summary(
    db: Session,
    account_id: Optional[str] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
) -> List[dict]:
    """Get cost breakdown by service for a date range."""
    stmt = select(
        BillingRecord.service,
        func.sum(BillingRecord.blended_cost).label("total_cost"),
        func.count().label("record_count"),
    )
    if account_id:
        stmt = stmt.where(BillingRecord.account_id == account_id)
    if start_date:
        stmt = stmt.where(BillingRecord.usage_date >= start_date)
    if end_date:
        stmt = stmt.where(BillingRecord.usage_date <= end_date)
    stmt = stmt.group_by(BillingRecord.service).order_by(func.sum(BillingRecord.blended_cost).desc())
    rows = db.execute(stmt).all()
    return [
        {"service": r.service, "total_cost": float(r.total_cost), "record_count": r.record_count}
        for r in rows
    ]


def get_daily_costs(
    db: Session,
    account_id: Optional[str] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
) -> List[dict]:
    """Get daily cost totals for forecasting."""
    stmt = select(
        BillingRecord.usage_date,
        func.sum(BillingRecord.blended_cost).label("daily_cost"),
    )
    if account_id:
        stmt = stmt.where(BillingRecord.account_id == account_id)
    if start_date:
        stmt = stmt.where(BillingRecord.usage_date >= start_date)
    if end_date:
        stmt = stmt.where(BillingRecord.usage_date <= end_date)
    stmt = stmt.group_by(BillingRecord.usage_date).order_by(BillingRecord.usage_date)
    rows = db.execute(stmt).all()
    return [
        {"date": r.usage_date, "cost": float(r.daily_cost)}
        for r in rows
    ]


def get_date_range(db: Session, account_id: Optional[str] = None) -> Tuple[Optional[date], Optional[date]]:
    stmt = select(
        func.min(BillingRecord.usage_date),
        func.max(BillingRecord.usage_date),
    )
    if account_id:
        stmt = stmt.where(BillingRecord.account_id == account_id)
    result = db.execute(stmt).first()
    if result and result[0]:
        return (result[0], result[1])
    return (None, None)


# --- Daily Aggregates (pre-computed for fast queries) ---

def refresh_daily_aggregates(db: Session, account_id: Optional[str] = None) -> int:
    """Recompute daily aggregates from raw billing records."""
    # Delete existing
    del_stmt = DailyCostAggregate.__table__.delete()
    if account_id:
        del_stmt = del_stmt.where(DailyCostAggregate.account_id == account_id)
    db.execute(del_stmt)

    # Recompute
    stmt = select(
        BillingRecord.account_id,
        BillingRecord.usage_date,
        BillingRecord.service,
        func.sum(BillingRecord.blended_cost).label("total_cost"),
        func.sum(BillingRecord.usage_quantity).label("total_usage"),
        func.count().label("record_count"),
    )
    if account_id:
        stmt = stmt.where(BillingRecord.account_id == account_id)
    stmt = stmt.group_by(
        BillingRecord.account_id,
        BillingRecord.usage_date,
        BillingRecord.service,
    )

    inserts = []
    for row in db.execute(stmt):
        inserts.append(DailyCostAggregate(
            account_id=row.account_id,
            usage_date=row.usage_date,
            service=row.service,
            total_cost=row.total_cost,
            total_usage=row.total_usage,
            record_count=row.record_count,
        ))

    if inserts:
        db.bulk_save_objects(inserts)
    db.flush()
    return len(inserts)


def get_aggregated_daily_costs(
    db: Session,
    account_id: str,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
) -> List[dict]:
    stmt = select(
        DailyCostAggregate.usage_date,
        func.sum(DailyCostAggregate.total_cost).label("daily_cost"),
    ).where(DailyCostAggregate.account_id == account_id)
    if start_date:
        stmt = stmt.where(DailyCostAggregate.usage_date >= start_date)
    if end_date:
        stmt = stmt.where(DailyCostAggregate.usage_date <= end_date)
    stmt = stmt.group_by(DailyCostAggregate.usage_date).order_by(DailyCostAggregate.usage_date)
    rows = db.execute(stmt).all()
    return [
        {"date": r.usage_date, "cost": float(r.daily_cost)}
        for r in rows
    ]


# --- Recommendations ---

def create_recommendation(
    db: Session,
    account_id: str,
    service: str,
    recommendation_type: str,
    estimated_monthly_savings: Decimal,
    description: str,
    details: Optional[str] = None,
    confidence: str = "medium",
) -> Recommendation:
    rec = Recommendation(
        account_id=account_id,
        service=service,
        recommendation_type=recommendation_type,
        estimated_monthly_savings=estimated_monthly_savings,
        description=description,
        details=details,
        confidence=confidence,
    )
    db.add(rec)
    db.flush()
    return rec


def get_recommendations(
    db: Session,
    account_id: Optional[str] = None,
    status: Optional[str] = None,
) -> List[Recommendation]:
    stmt = select(Recommendation)
    if account_id:
        stmt = stmt.where(Recommendation.account_id == account_id)
    if status:
        stmt = stmt.where(Recommendation.status == status)
    stmt = stmt.order_by(Recommendation.created_at.desc())
    return db.execute(stmt).scalars().all()


def get_recommendations_summary(db: Session, account_id: str) -> dict:
    """Get total estimated savings by type."""
    stmt = select(
        Recommendation.recommendation_type,
        func.sum(Recommendation.estimated_monthly_savings).label("total_savings"),
        func.count().label("count"),
    ).where(Recommendation.account_id == account_id).group_by(Recommendation.recommendation_type)
    rows = db.execute(stmt).all()
    return {
        r.recommendation_type: {"total_savings": float(r.total_savings), "count": r.count}
        for r in rows
    }