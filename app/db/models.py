"""SQLAlchemy models for billing data."""
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Account(Base):
    """Cloud billing accounts."""
    __tablename__ = "accounts"

    account_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    account_name: Mapped[str] = mapped_column(String(255), nullable=False)
    environment: Mapped[str] = mapped_column(String(50), nullable=False)  # dev, staging, prod
    provider: Mapped[str] = mapped_column(String(50), default="AWS")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    billing_records: Mapped[list["BillingRecord"]] = relationship(back_populates="account")
    recommendations: Mapped[list["Recommendation"]] = relationship(back_populates="account")


class BillingRecord(Base):
    """Raw billing line items from cloud provider exports."""
    __tablename__ = "billing_records"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    account_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("accounts.account_id"), nullable=False, index=True
    )
    usage_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    service: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    usage_type: Mapped[str] = mapped_column(String(255), nullable=False)
    operation: Mapped[str] = mapped_column(String(255), nullable=False)
    region: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    usage_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    unit: Mapped[str] = mapped_column(String(64), nullable=False)
    blended_cost: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    currency: Mapped[str] = mapped_column(String(10), default="USD")
    line_item_description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    invoice_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    ingestion_timestamp: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    account: Mapped[Account] = relationship(back_populates="billing_records")

    __table_args__ = (
        Index("ix_billing_account_date_service", "account_id", "usage_date", "service"),
        Index("ix_billing_account_date", "account_id", "usage_date"),
    )


class Recommendation(Base):
    """Generated cost optimization recommendations."""
    __tablename__ = "recommendations"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    account_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("accounts.account_id"), nullable=False, index=True
    )
    service: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    recommendation_type: Mapped[str] = mapped_column(
        String(64), nullable=False
    )  # right_sizing, reserved_instances, savings_plans, storage_lifecycle, anomaly
    estimated_monthly_savings: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    details: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON with specifics
    confidence: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)  # high, medium, low
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending, applied, dismissed
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    account: Mapped[Account] = relationship(back_populates="recommendations")


class DailyCostAggregate(Base):
    """Pre-computed daily cost aggregations for fast queries."""
    __tablename__ = "daily_cost_aggregates"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    account_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    usage_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    service: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    total_cost: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    total_usage: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    record_count: Mapped[int] = mapped_column(BigInteger, default=0)

    __table_args__ = (
        UniqueConstraint("account_id", "usage_date", "service", name="uq_daily_aggregate"),
    )