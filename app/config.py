"""Configuration for Cost Intelligence Agent."""
import os
from pathlib import Path
from typing import Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # App
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    app_env: str = "development"
    log_level: str = "INFO"

    # Ollama
    ollama_base_url: str = "http://localhost:11434"
    ollama_chat_model: str = "llama3.2:3b"
    ollama_embed_model: str = "nomic-embed-text"
    ollama_timeout: int = 120

    # PostgreSQL
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "cost_intelligence"
    postgres_user: str = "cost_user"
    postgres_password: str = "cost_password"
    postgres_pool_size: int = 5
    postgres_max_overflow: int = 10

    # ChromaDB
    chroma_host: str = "localhost"
    chroma_port: int = 8001
    chroma_collection: str = "cost_optimization_patterns"
    chroma_persist_dir: str = "./data/chroma"

    # Redis
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0
    redis_cache_ttl: int = 3600
    redis_enabled: bool = True

    # Forecasting
    forecast_horizon_days: int = 90
    forecast_holdout_days: int = 30
    mape_threshold: float = 15.0

    # Data
    sample_data_path: str = "./data/sample_billing_data.csv"

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+psycopg2://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def ollama_embed_url(self) -> str:
        return f"{self.ollama_base_url}/api/embeddings"

    @property
    def ollama_generate_url(self) -> str:
        return f"{self.ollama_base_url}/api/generate"

    @property
    def ollama_chat_url(self) -> str:
        return f"{self.ollama_base_url}/api/chat"


settings = Settings()

# Ensure data directories exist
Path(settings.chroma_persist_dir).mkdir(parents=True, exist_ok=True)
Path(settings.sample_data_path).parent.mkdir(parents=True, exist_ok=True)