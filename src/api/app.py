"""FastAPI application for TWC Alerts."""

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

from .routes import router, init_repos
from ..alerts.repository import AlertRepository
from ..data.repository import MetricRepository


def get_config_from_env() -> dict:
    """Get ClickHouse config from environment variables."""
    return {
        "host": os.getenv("CLICKHOUSE_HOST", "localhost"),
        "port": int(os.getenv("CLICKHOUSE_PORT", "8123")),
        "username": os.getenv("CLICKHOUSE_USER", "default"),
        "password": os.getenv("CLICKHOUSE_PASSWORD", ""),
        "database": os.getenv("CLICKHOUSE_DATABASE", "default"),
    }


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize resources on startup."""
    config = get_config_from_env()

    alert_repo = AlertRepository(**config)
    metric_repo = MetricRepository(**config)

    # Ensure table exists
    alert_repo.create_table()

    # Initialize route handlers with repos
    init_repos(alert_repo, metric_repo)

    yield


app = FastAPI(
    title="TWC Alerts API",
    description="Anomaly detection and alerting for TWC metrics",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(router)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "src.api.app:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8000")),
        reload=True,
    )
