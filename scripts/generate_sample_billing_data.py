#!/usr/bin/env python3
"""Generate synthetic AWS Cost Explorer style billing data."""
import csv
import random
from datetime import date, timedelta
from pathlib import Path


def generate_aws_billing_data(
    num_days: int = 365,
    num_accounts: int = 3,
    output_path: str = "./data/sample_billing_data.csv",
) -> None:
    """Generate realistic synthetic AWS billing data."""

    accounts = {
        "111111111111": ("Development Account", "dev"),
        "222222222222": ("Staging Account", "staging"),
        "333333333333": ("Production Account", "production"),
    }

    services = {
        "Amazon Elastic Compute Cloud - Compute": {
            "usage_types": ["BoxUsage:c5.large", "BoxUsage:c5.xlarge", "BoxUsage:r5.large", "BoxUsage:t3.medium"],
            "operations": ["RunInstances"],
            "base_daily_cost": 50.0,
            "variance": 0.3,
            "trend": 0.001,  # slight upward trend
        },
        "Amazon Simple Storage Service": {
            "usage_types": ["Storage-ByteHrs", "Requests-Tier1", "DataTransfer-Out-Bytes"],
            "operations": ["PutObject", "GetObject", "ListObjects"],
            "base_daily_cost": 20.0,
            "variance": 0.2,
            "trend": 0.0005,
        },
        "Amazon Relational Database Service": {
            "usage_types": ["RDS:StorageUsage", "RDS:InstanceUsage:db.r5.large", "RDS:InstanceUsage:db.t3.medium"],
            "operations": ["RunInstances"],
            "base_daily_cost": 30.0,
            "variance": 0.15,
            "trend": 0.0008,
        },
        "AmazonCloudWatch": {
            "usage_types": ["MetricMonitorUsage", "AlarmUsage", "LogStorage-ByteHrs"],
            "operations": ["GetMetricData", "PutMetricData"],
            "base_daily_cost": 5.0,
            "variance": 0.4,
            "trend": 0.002,
        },
        "Amazon DynamoDB": {
            "usage_types": ["DDB:ReadCapacityUnit", "DDB:WriteCapacityUnit", "DDB:StorageUsage"],
            "operations": ["GetItem", "PutItem", "Query"],
            "base_daily_cost": 15.0,
            "variance": 0.25,
            "trend": 0.001,
        },
        "Amazon Virtual Private Cloud": {
            "usage_types": ["NATGateway-Bytes", "NATGateway-Hours", "DataTransfer-Out-Bytes"],
            "operations": ["NatGateway"],
            "base_daily_cost": 10.0,
            "variance": 0.2,
            "trend": 0.0,
        },
        "AWS Key Management Service": {
            "usage_types": ["KMS:Requests", "KMS:KeyStorage"],
            "operations": ["Encrypt", "Decrypt", "GenerateDataKey"],
            "base_daily_cost": 2.0,
            "variance": 0.1,
            "trend": 0.0,
        },
        "AWS Lambda": {
            "usage_types": ["Lambda-GB-Second", "Lambda-Request", "Lambda-Provisioned-GB-Second"],
            "operations": ["Invoke"],
            "base_daily_cost": 8.0,
            "variance": 0.5,
            "trend": 0.0015,
        },
    }

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "Account ID", "Account Name", "Service", "Usage Type", "Operation",
            "Cost", "Currency", "Usage Quantity", "Unit",
            "Billing Period Start Date", "Billing Period End Date",
            "Invoice ID", "Line Item Description"
        ])

        invoice_counter = 1000

        for day_offset in range(num_days):
            billing_date = date.today() - timedelta(days=num_days - 1 - day_offset)

            for account_id, (account_name, environment) in accounts.items():
                # Environment multipliers
                env_multiplier = {"dev": 0.3, "staging": 0.6, "production": 1.0}[environment]

                for service_name, config in services.items():
                    # Base cost with trend
                    base = config["base_daily_cost"] * env_multiplier
                    trend_factor = 1 + (config["trend"] * day_offset)

                    # Add weekly seasonality (lower on weekends)
                    day_of_week = billing_date.weekday()
                    weekend_factor = 0.7 if day_of_week >= 5 else 1.0

                    # Add random variance
                    variance = random.uniform(1 - config["variance"], 1 + config["variance"])

                    daily_cost = base * trend_factor * weekend_factor * variance

                    # Distribute cost across usage types
                    num_usage_types = random.randint(1, len(config["usage_types"]))
                    selected_types = random.sample(config["usage_types"], num_usage_types)

                    for usage_type in selected_types:
                        operation = random.choice(config["operations"])
                        type_cost = daily_cost / num_usage_types

                        # Generate invoice ID periodically
                        if random.random() < 0.02:
                            invoice_counter += 1

                        usage_qty = round(type_cost / random.uniform(0.01, 0.1), 4)

                        writer.writerow([
                            account_id,
                            account_name,
                            service_name,
                            usage_type,
                            operation,
                            round(type_cost, 4),
                            "USD",
                            usage_qty,
                            "USD" if "Storage" in usage_type or "Usage" in usage_type else "Hours",
                            billing_date.isoformat(),
                            billing_date.isoformat(),
                            f"INV-{billing_date.year}{billing_date.month:02d}-{invoice_counter:05d}",
                            f"{service_name} - {usage_type} on {billing_date.isoformat()}"
                        ])

    print(f"Generated {num_days} days of billing data for {num_accounts} accounts at {output_path}")


def main():
    generate_aws_billing_data(
        num_days=365,
        num_accounts=3,
        output_path=str(Path(__file__).parent.parent / "data" / "sample_billing_data.csv"),
    )


if __name__ == "__main__":
    main()