"""Cost Intelligence Agent - FastAPI application entry point."""
import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import billing, chat
from app.config import settings
from app.db.session import init_db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan handler."""
    logger.info("Starting Cost Intelligence Agent...")
    init_db()
    logger.info("Database initialized")
    yield
    logger.info("Shutting down Cost Intelligence Agent...")


app = FastAPI(
    title="Cost Intelligence Agent",
    description="Autonomous cloud cost analysis and optimization agent with LangGraph",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(billing.router)
app.include_router(chat.router)


@app.get("/health", tags=["health"])
async def health_check():
    """Health check endpoint."""
    return {"status": "ok", "service": "cost-intelligence-agent"}


@app.get("/", tags=["root"])
async def root():
    """Root endpoint."""
    return {
        "service": "Cost Intelligence Agent",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health",
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=settings.app_env == "development",
    )