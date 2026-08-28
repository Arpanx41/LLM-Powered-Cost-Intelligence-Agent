"""Billing data ingestion from CSV (AWS Cost Explorer format)."""
import csv
import logging
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from app.db.crud import upsert_account
from app.db.models import Account, BillingRecord
from app.db.session import session_scope

logger = logging.getLogger(__name__)

# Expected AWS Cost Explorer CSV columns
EXPECTED_COLUMNS = [
    "Account ID",
    "Account Name",
    "Service",
    "Usage Type",
    "Operation",
    "Cost",
    "Currency",
    "Usage Quantity",
    "Unit",
    "Billing Period Start Date",
    "Billing Period End Date",
    "Invoice ID",
    "Line Item Description",
]


def parse_date(date_str: str) -> date:
    """Parse date from various formats."""
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(date_str, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Unable to parse date: {date_str}")


def parse_decimal(value: str) -> Decimal:
    """Parse decimal, handling empty strings."""
    if not value or value.strip() == "":
        return Decimal("0")
    return Decimal(value.replace(",", ""))


def ingest_billing_csv(
    file_path: str,
    db: Optional[Session] = None,
    default_account_id: Optional[str] = None,
    default_environment: str = "production",
) -> int:
    """
    Ingest AWS Cost Explorer CSV into database.

    Returns number of records ingested.
    """
    if db is None:
        # Use session scope
        with session_scope() as session:
            return _ingest_csv(session, file_path, default_account_id, default_environment)
    else:
        return _ingest_csv(db, file_path, default_account_id, default_environment)


def _ingest_csv(
    db: Session,
    file_path: str,
    default_account_id: Optional[str] = None,
    default_environment: str = "production",
) -> int:
    records_to_insert = []
    accounts_seen = set()

    with open(file_path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []

        # Validate columns
        missing = set(EXPECTED_COLUMNS) - set(fieldnames)
        if missing:
            logger.warning("CSV missing expected columns: %s", missing)

        for row in reader:
            account_id = row.get("Account ID") or default_account_id
            if not account_id:
                logger.warning("Skipping row without account ID")
                continue

            account_name = row.get("Account Name") or f"Account {account_id}"

            # Upsert account
            if account_id not in accounts_seen:
                upsert_account(db, account_id, account_name, default_environment)
                accounts_seen.add(account_id)

            # Parse billing record
            try:
                usage_date = parse_date(row.get("Billing Period Start Date", ""))
            except ValueError:
                logger.warning("Invalid date in row, skipping: %s", row)
                continue

            record = BillingRecord(
                account_id=account_id,
                usage_date=usage_date,
                service=row.get("Service", "Unknown"),
                usage_type=row.get("Usage Type", ""),
                operation=row.get("Operation", ""),
                region="us-east-1",  # Not in standard CE export; would need CUR
                usage_quantity=parse_decimal(row.get("Usage Quantity", "0")),
                unit=row.get("Unit", ""),
                blended_cost=parse_decimal(row.get("Cost", "0")),
                currency=row.get("Currency", "USD"),
                line_item_description=row.get("Line Item Description"),
                invoice_id=row.get("Invoice ID"),
            )
            records_to_insert.append(record)

    # Bulk insert
    if records_to_insert:
        from app.db.crud import bulk_insert_billing_records
        count = bulk_insert_billing_records(db, records_to_insert)
        logger.info("Ingested %d billing records for accounts: %s", count, accounts_seen)
        return count

    return 0