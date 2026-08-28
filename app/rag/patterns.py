"""Cost optimization patterns for RAG retrieval."""
# These patterns are embedded and stored in ChromaDB for the agent to retrieve
# when analyzing billing data.

OPTIMIZATION_PATTERNS = [
    {
        "id": "ec2_rightsizing",
        "category": "right_sizing",
        "services": ["Amazon Elastic Compute Cloud - Compute"],
        "content": """
EC2 Right-Sizing Pattern:
- Identify instances with consistently low CPU utilization (< 20% average over 14 days)
- Check memory utilization patterns to determine if instance is memory-bound or CPU-bound
- Downsize to smaller instance type within same family (e.g., c5.large → c5.medium)
- For burstable workloads, consider T3/T4g instances with CPU credits
- Expected savings: 30-50% per right-sized instance
- Risk: Low if monitoring confirms sustained low utilization
""",
    },
    {
        "id": "ec2_reserved_instances",
        "category": "reserved_instances",
        "services": ["Amazon Elastic Compute Cloud - Compute"],
        "content": """
EC2 Reserved Instances / Savings Plans Pattern:
- Analyze steady-state workloads running 24/7 for at least 1 year
- Compare On-Demand vs 1-year/3-year Reserved Instance pricing
- Use Compute Savings Plans for flexibility across instance families
- Target services: EC2, RDS, ElastiCache, Redshift
- Expected savings: 30-72% vs On-Demand depending on term
- Risk: Low for stable workloads; use Savings Plans for flexibility
""",
    },
    {
        "id": "s3_storage_lifecycle",
        "category": "storage_lifecycle",
        "services": ["Amazon Simple Storage Service"],
        "content": """
S3 Storage Lifecycle Pattern:
- Identify buckets with large amounts of infrequently accessed data
- Transition to S3 Standard-IA after 30 days of no access
- Transition to Glacier Instant Retrieval after 90 days
- Transition to Glacier Deep Archive after 365 days for compliance archives
- Enable S3 Intelligent-Tiering for unpredictable access patterns
- Delete incomplete multipart uploads after 7 days
- Expected savings: 40-95% on storage costs depending on tier
- Risk: Very low; retrieval fees apply for Glacier tiers
""",
    },
    {
        "id": "rds_rightsizing",
        "category": "right_sizing",
        "services": ["Amazon Relational Database Service"],
        "content": """
RDS Right-Sizing Pattern:
- Monitor CPU, memory, and IOPS utilization over 14+ days
- Downsize instance class if CPU < 30% and memory < 50% consistently
- Consider changing from provisioned IOPS to gp3 storage for better price/performance
- For multi-AZ deployments, evaluate if single-AZ is sufficient for dev/staging
- Use Aurora Serverless v2 for variable/unpredictable workloads
- Expected savings: 20-60% on compute; 20% on storage with gp3
- Risk: Medium; test in staging before production changes
""",
    },
    {
        "id": "lambda_optimization",
        "category": "right_sizing",
        "services": ["AWS Lambda"],
        "content": """
Lambda Optimization Pattern:
- Right-size memory allocation: test 128MB, 256MB, 512MB, 1024MB, 2048MB, 3008MB
- Higher memory often reduces duration, lowering total cost (GB-seconds)
- Use AWS Lambda Power Tuning tool for automated optimization
- Enable provisioned concurrency only for latency-sensitive functions with steady traffic
- Consolidate small functions to reduce cold starts
- Expected savings: 10-50% through memory right-sizing
- Risk: Low; easily reversible
""",
    },
    {
        "id": "dynamodb_optimization",
        "category": "right_sizing",
        "services": ["Amazon DynamoDB"],
        "content": """
DynamoDB Optimization Pattern:
- Switch from provisioned to on-demand capacity for unpredictable workloads
- Use DynamoDB Standard-IA table class for infrequently accessed tables
- Enable TTL for automatic expiration of temporary data
- Use sparse GSIs to reduce index storage costs
- Monitor consumed vs provisioned RCU/WCU; adjust or switch modes
- Expected savings: 30-60% with on-demand for variable traffic
- Risk: Low for on-demand; IA class has higher per-request cost
""",
    },
    {
        "id": "ebs_optimization",
        "category": "right_sizing",
        "services": ["Amazon Elastic Block Store"],
        "content": """
EBS Volume Optimization Pattern:
- Identify unattached volumes (orphaned after instance termination)
- Convert gp2 volumes to gp3 for 20% lower cost + better baseline performance
- Delete snapshots older than retention policy (e.g., 90 days)
- Use Data Lifecycle Manager for automated snapshot management
- Shrink oversized volumes (if filesystem supports it) or migrate to smaller volumes
- Expected savings: 20% on gp2→gp3; 100% on orphaned volumes
- Risk: Low for gp3 conversion; medium for volume shrinking
""",
    },
    {
        "id": "cloudwatch_optimization",
        "category": "right_sizing",
        "services": ["AmazonCloudWatch"],
        "content": """
CloudWatch Cost Optimization Pattern:
- Reduce custom metric resolution (1-min → 5-min) where high fidelity isn't needed
- Delete unused custom metrics and namespaces
- Set log retention policies (default is infinite)
- Use metric filters instead of custom metrics where possible
- Consolidate alarms; remove alarms on terminated resources
- Expected savings: 30-80% on custom metrics and logs
- Risk: Low; verify monitoring coverage before reducing
""",
    },
    {
        "id": "data_transfer_optimization",
        "category": "right_sizing",
        "services": ["Amazon Virtual Private Cloud", "Amazon Elastic Compute Cloud - Compute"],
        "content": """
Data Transfer Cost Optimization Pattern:
- Use VPC endpoints (Gateway/Interface) for S3/DynamoDB to eliminate NAT gateway charges
- Consolidate inter-AZ traffic; keep services in same AZ where possible
- Use CloudFront for external traffic instead of direct ALB/EC2 egress
- Enable S3 Transfer Acceleration only when needed
- Monitor NAT Gateway data processing charges; consider NAT instance for low traffic
- Expected savings: $0.01/GB on NAT Gateway; up to 100% with VPC endpoints
- Risk: Low for VPC endpoints; medium for architecture changes
""",
    },
    {
        "id": "kms_optimization",
        "category": "right_sizing",
        "services": ["AWS Key Management Service"],
        "content": """
KMS Cost Optimization Pattern:
- Delete unused customer managed keys (CMKs)
- Disable automatic key rotation for keys not requiring compliance rotation
- Use AWS managed keys (free) instead of CMKs where possible
- Consolidate keys used for same purpose
- Expected savings: $1/month per CMK + $1/month for rotation
- Risk: Low; verify compliance requirements before disabling rotation
""",
    },
    {
        "id": "anomaly_detection",
        "category": "anomaly",
        "services": ["*"],
        "content": """
Cost Anomaly Detection Pattern:
- Establish baseline: 30-day rolling average cost per service/account
- Flag daily cost spikes > 2 standard deviations from baseline
- Correlate spikes with: new resource deployment, traffic surge, misconfiguration
- Common anomalies: runaway Lambda invocations, forgotten dev resources, DDoS traffic
- Set up billing alerts at 110%, 125%, 150% of forecasted monthly spend
- Expected value: Early detection prevents runaway costs
- Risk: None (detection only); action required for remediation
""",
    },
    {
        "id": "savings_plans_management",
        "category": "reserved_instances",
        "services": ["*"],
        "content": """
Savings Plans Management Pattern:
- Monitor Savings Plans utilization daily (target > 85%)
- Use Compute Savings Plans for EC2/Fargate/Lambda flexibility
- Use EC2 Instance Savings Plans for specific instance family commitment
- Queue additional Savings Plans purchases when utilization consistently > 95%
- Set up alerts for utilization dropping below 70%
- Expected savings: 30-72% vs On-Demand with full utilization
- Risk: Medium; commitment lock-in; monitor utilization closely
""",
    },
]


def get_all_patterns():
    return OPTIMIZATION_PATTERNS


def get_patterns_by_service(service: str):
    """Filter patterns relevant to a specific service."""
    results = []
    for p in OPTIMIZATION_PATTERNS:
        if "*" in p["services"] or service in p["services"]:
            results.append(p)
    return results


def get_patterns_by_category(category: str):
    """Filter patterns by recommendation category."""
    return [p for p in OPTIMIZATION_PATTERNS if p["category"] == category]