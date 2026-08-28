# Cost Intelligence Agent

An autonomous cloud cost analysis and optimization agent built with **LangGraph**, **FastAPI**, and local LLMs via **Ollama**. Analyzes AWS billing data, generates cost forecasts with MAPE validation, and provides actionable optimization recommendations.

## Features

- **LangGraph Workflow**: Multi-step agent with query parsing, data retrieval, analysis, recommendations, forecasting, and response generation
- **Local LLMs**: Runs entirely offline with Ollama (llama3.2, nomic-embed-text)
- **AWS Billing Ingestion**: Parses Cost Explorer CSV format into PostgreSQL
- **RAG Optimization Patterns**: 12 built-in cost optimization patterns retrieved via ChromaDB embeddings
- **Forecasting**: Simple Moving Average with trend + holdout MAPE validation
- **Anomaly Detection**: Statistical spike detection on daily costs
- **FastAPI + Swagger UI**: Interactive API docs at `/docs`
- **Docker Compose**: One-command local stack (API, PostgreSQL, ChromaDB, Redis, Ollama)
- **Kubernetes Manifests**: Production-ready K8s deployments with PVCs

## Architecture

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│   Client    │────▶│  FastAPI     │────▶│  LangGraph  │
│  (Swagger)  │     │   API        │     │   Agent     │
└─────────────┘     └──────┬───────┘     └──────┬──────┘
                           │                    │
                    ┌──────▼──────┐     ┌───────▼────────┐
                    │ PostgreSQL  │     │  ChromaDB      │
                    │ (Billing)   │     │  (Patterns)    │
                    └─────────────┘     └────────────────┘
                           │
                    ┌──────▼──────┐
                    │   Ollama    │
                    │ (LLM + Emb) │
                    └─────────────┘
```

## Quick Start

### Prerequisites

- Docker & Docker Compose
- 8GB+ RAM (for Ollama models)

### 1. Clone and Start

```bash
cd cost-intelligence-agent
docker compose up -d
```

This starts:
- **API** at http://localhost:8000
- **Swagger UI** at http://localhost:8000/docs
- **Ollama** at http://localhost:11434
- **PostgreSQL** at localhost:5432
- **ChromaDB** at http://localhost:8001
- **Redis** at localhost:6379

### 2. Pull Models

```bash
docker exec -it cost-intelligence-agent-ollama-1 ollama pull llama3.2:3b
docker exec -it cost-intelligence-agent-ollama-1 ollama pull nomic-embed-text
```

### 3. Generate & Ingest Sample Data

```bash
# Via API
curl -X POST http://localhost:8000/billing/generate-sample-data

# Or directly
docker compose exec app python scripts/generate_sample_billing_data.py
docker compose exec app python scripts/init_optimization_patterns.py
```

### 4. Query the Agent

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"query": "What are my top costs and how can I optimize them?"}'
```

## API Reference

### Billing Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/billing/accounts` | List all billing accounts |
| GET | `/billing/summary` | Cost summary by service (date range) |
| GET | `/billing/daily-costs` | Daily costs for forecasting |
| GET | `/billing/records` | Raw billing records with filters |
| POST | `/billing/generate-sample-data` | Generate & ingest synthetic data |
| POST | `/billing/ingest` | Ingest CSV file |
| POST | `/billing/refresh-aggregates` | Refresh daily cost aggregates |

### Chat Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/chat` | Main agent query endpoint |
| GET | `/chat/recommendations` | List stored recommendations |
| GET | `/chat/recommendations/summary` | Recommendations by type |
| GET | `/chat/forecast/{account_id}` | Cost forecast with MAPE validation |

### Example Queries

```bash
# Cost summary
curl -X POST http://localhost:8000/chat \
  -d '{"query": "Show me cost breakdown for last 30 days"}'

# Recommendations
curl -X POST http://localhost:8000/chat \
  -d '{"query": "How can I reduce my EC2 costs?"}'

# Forecast
curl -X POST http://localhost:8000/chat \
  -d '{"query": "Forecast my costs for next 90 days"}'

# Anomalies
curl -X POST http://localhost:8000/chat \
  -d '{"query": "Any unusual spending recently?"}'

# Specific account
curl -X POST http://localhost:8000/chat \
  -d '{"query": "Optimize costs for account 111111111111", "account_id": "111111111111"}'
```

## Configuration

Environment variables (`.env`):

```bash
# Ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_CHAT_MODEL=llama3.2:3b
OLLAMA_EMBED_MODEL=nomic-embed-text

# PostgreSQL
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=cost_intelligence
POSTGRES_USER=cost_user
POSTGRES_PASSWORD=cost_password
POSTGRES_POOL_SIZE=5
POSTGRES_MAX_OVERFLOW=10

# ChromaDB
CHROMA_HOST=localhost
CHROMA_PORT=8001
CHROMA_COLLECTION=cost_optimization_patterns

# Redis
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_CACHE_TTL=3600
REDIS_ENABLED=true

# Forecasting
FORECAST_HORIZON_DAYS=90
FORECAST_HOLDOUT_DAYS=30
MAPE_THRESHOLD=15.0
```

## Project Structure

```
cost-intelligence-agent/
├── app/
│   ├── agents/           # LangGraph workflow
│   │   ├── cost_agent.py # Agent nodes & workflow
│   │   └── state.py      # AgentState dataclass
│   ├── api/
│   │   └── routes/       # FastAPI routes (billing, chat)
│   ├── db/
│   │   ├── models.py     # SQLAlchemy models
│   │   ├── session.py    # DB session management
│   │   └── crud.py       # Database operations
│   ├── rag/
│   │   ├── patterns.py   # 12 optimization patterns
│   │   └── retriever.py  # ChromaDB vector retrieval
│   ├── services/
│   │   ├── embeddings.py # Ollama embeddings
│   │   ├── forecasting.py # SMA + MAPE validation
│   │   └── billing_ingestion.py # CSV ingestion
│   ├── config.py         # Pydantic settings
│   ├── schemas.py        # Pydantic request/response models
│   └── main.py           # FastAPI app entry
├── scripts/
│   ├── generate_sample_billing_data.py  # Synthetic AWS CE data
│   └── init_optimization_patterns.py    # ChromaDB pattern init
├── tests/
│   ├── test_forecasting.py
│   └── test_agent.py
├── k8s/
│   ├── deployment.yaml
│   ├── service.yaml
│   └── configmap.yaml
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
└── .env.example
```

## Optimization Patterns (RAG)

The agent includes 12 built-in patterns:

| Pattern | Category | Service |
|---------|----------|---------|
| EC2 Rightsizing | Compute | EC2 |
| Reserved Instances | Compute | EC2 |
| S3 Lifecycle | Storage | S3 |
| RDS Rightsizing | Database | RDS |
| Lambda Optimization | Serverless | Lambda |
| DynamoDB Optimization | Database | DynamoDB |
| EBS Volume Optimization | Storage | EBS |
| CloudWatch Cost Control | Monitoring | CloudWatch |
| Data Transfer Optimization | Network | VPC |
| KMS Cost Optimization | Security | KMS |
| Anomaly Detection | Anomaly | All |
| Savings Plans | Compute | EC2/Fargate/Lambda |

Patterns are embedded with `nomic-embed-text` and retrieved by semantic similarity.

## Forecasting

- **Method**: Simple Moving Average (30-day window) + linear trend
- **Validation**: Holdout MAPE (30 days default)
- **Threshold**: MAPE ≤ 15% for reliable forecasts
- **Output**: Daily forecasts + model metadata + validation results

## Kubernetes Deployment

```bash
# Apply manifests
kubectl apply -f k8s/configmap.yaml
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/service.yaml

# Update secret with real password
kubectl create secret generic cost-intelligence-secrets \
  --from-literal=POSTGRES_PASSWORD='your-secure-password'
```

## Testing

```bash
# Run all tests
docker compose exec app pytest tests/ -v

# Specific test modules
docker compose exec app pytest tests/test_forecasting.py -v
docker compose exec app pytest tests/test_agent.py -v
```

## Development

```bash
# Install deps locally
pip install -r requirements.txt

# Run API locally (needs services running)
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Format code
black app/ tests/
ruff check app/ tests/
```

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Ollama model not found | `docker exec -it <ollama-container> ollama pull llama3.2:3b` |
| ChromaDB connection refused | Check `docker compose logs chromadb` |
| PostgreSQL auth failed | Verify credentials in `.env` match docker-compose |
| Agent returns template response | Ollama not reachable; check `OLLAMA_BASE_URL` |
| High MAPE | Need more historical data (≥ 90 days recommended) |

## License

MIT