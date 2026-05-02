"""API routes for alerts."""

from datetime import date
from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from ..alerts.models import AlertStatus
from ..alerts.repository import AlertRepository
from ..data.repository import MetricRepository
from ..core.metrics import get_all_metrics, get_metric
from ..core.anomaly import detect_anomaly

router = APIRouter(prefix="/api/v1/alerts", tags=["alerts"])

# Repositories (initialized by app.py)
alert_repo: Optional[AlertRepository] = None
metric_repo: Optional[MetricRepository] = None


def init_repos(alert_repository: AlertRepository, metric_repository: MetricRepository):
    """Initialize repositories."""
    global alert_repo, metric_repo
    alert_repo = alert_repository
    metric_repo = metric_repository


# =============================================================================
# Request/Response Models
# =============================================================================

class AlertListResponse(BaseModel):
    """Response containing list of alerts."""
    alerts: list[dict]
    total: int


class AlertResponse(BaseModel):
    """Single alert response."""
    alert: dict


class UpdateAlertRequest(BaseModel):
    """Request to update alert status."""
    status: str  # "acknowledged", "resolved", "dismissed"
    acknowledged_by: Optional[str] = None
    notes: Optional[str] = None


class MetricCheckRequest(BaseModel):
    """Request to manually check a metric."""
    metric_name: str
    target_date: Optional[str] = None  # ISO format, defaults to yesterday


class MetricCheckResponse(BaseModel):
    """Response from metric check."""
    metric_name: str
    tenant_id: str
    date: str
    current_value: float
    baseline_median: float
    z_score: float
    is_anomaly: bool
    anomaly_type: Optional[str]
    percentage_change: float


# =============================================================================
# Routes
# =============================================================================

@router.get("/{tenant_id}")
async def get_alerts(
    tenant_id: str,
    status: Optional[str] = Query(None, description="Filter by status"),
    days: int = Query(30, ge=1, le=365, description="Days of history"),
    limit: int = Query(100, ge=1, le=500, description="Max alerts to return"),
) -> AlertListResponse:
    """
    Get alerts for a tenant.

    Args:
        tenant_id: Tenant ID
        status: Filter by status (active, acknowledged, resolved, dismissed)
        days: Number of days of history to include
        limit: Maximum number of alerts to return
    """
    if not alert_repo:
        raise HTTPException(status_code=503, detail="Service not initialized")

    alert_status = AlertStatus(status) if status else None
    alerts = alert_repo.get_alerts_for_tenant(tenant_id, alert_status, days, limit)

    return AlertListResponse(
        alerts=[a.to_dict() for a in alerts],
        total=len(alerts),
    )


@router.get("/{tenant_id}/active")
async def get_active_alerts(tenant_id: str) -> AlertListResponse:
    """Get all active (unacknowledged) alerts for a tenant."""
    if not alert_repo:
        raise HTTPException(status_code=503, detail="Service not initialized")

    alerts = alert_repo.get_active_alerts(tenant_id)

    return AlertListResponse(
        alerts=[a.to_dict() for a in alerts],
        total=len(alerts),
    )


@router.get("/{tenant_id}/{alert_id}")
async def get_alert(tenant_id: str, alert_id: str) -> AlertResponse:
    """Get a single alert by ID."""
    if not alert_repo:
        raise HTTPException(status_code=503, detail="Service not initialized")

    alert = alert_repo.get_alert(alert_id)

    if not alert or alert.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Alert not found")

    return AlertResponse(alert=alert.to_dict())


@router.put("/{tenant_id}/{alert_id}")
async def update_alert(
    tenant_id: str,
    alert_id: str,
    request: UpdateAlertRequest,
) -> AlertResponse:
    """
    Update alert status.

    Status transitions:
    - active -> acknowledged, resolved, dismissed
    - acknowledged -> resolved, dismissed
    """
    if not alert_repo:
        raise HTTPException(status_code=503, detail="Service not initialized")

    try:
        new_status = AlertStatus(request.status)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status. Must be one of: {[s.value for s in AlertStatus]}"
        )

    success = alert_repo.update_status(
        alert_id,
        new_status,
        acknowledged_by=request.acknowledged_by,
        notes=request.notes,
    )

    if not success:
        raise HTTPException(status_code=404, detail="Alert not found")

    alert = alert_repo.get_alert(alert_id)
    return AlertResponse(alert=alert.to_dict())


@router.post("/{tenant_id}/check")
async def check_metric(
    tenant_id: str,
    request: MetricCheckRequest,
) -> MetricCheckResponse:
    """
    Manually check a metric for anomalies.

    Useful for testing or debugging without waiting for the CRON job.
    """
    if not alert_repo or not metric_repo:
        raise HTTPException(status_code=503, detail="Service not initialized")

    metric = get_metric(request.metric_name)
    if not metric:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown metric: {request.metric_name}"
        )

    target_date = date.fromisoformat(request.target_date) if request.target_date else date.today()

    current, historical = metric_repo.get_metric_with_baseline(
        metric, tenant_id, target_date, baseline_weeks=8
    )

    result = detect_anomaly(
        metric_name=metric.name,
        tenant_id=tenant_id,
        date=target_date.isoformat(),
        current_value=current,
        historical_values=historical,
        drop_threshold=metric.drop_threshold,
        spike_threshold=metric.spike_threshold,
        min_volume=metric.min_volume,
        min_history_weeks=metric.min_history_weeks,
    )

    return MetricCheckResponse(
        metric_name=result.metric_name,
        tenant_id=result.tenant_id,
        date=result.date,
        current_value=result.current_value,
        baseline_median=result.baseline.median,
        z_score=result.z_score,
        is_anomaly=result.is_anomaly,
        anomaly_type=result.anomaly_type,
        percentage_change=result.percentage_change,
    )


@router.get("/metrics/list")
async def list_metrics() -> dict:
    """List all available metrics."""
    metrics = get_all_metrics()
    return {
        "metrics": [
            {
                "name": m.name,
                "display_name": m.display_name,
                "description": m.description,
                "unit": m.unit,
                "drop_threshold": m.drop_threshold,
                "spike_threshold": m.spike_threshold,
                "min_volume": m.min_volume,
            }
            for m in metrics
        ]
    }
