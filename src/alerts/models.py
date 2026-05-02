"""Alert models and storage."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from enum import Enum


class AlertStatus(Enum):
    """Status of an alert."""
    ACTIVE = "active"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"  # User marked as expected


class AlertSeverity(Enum):
    """Severity levels for alerts."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class Alert:
    """An alert generated from anomaly detection."""
    id: str
    tenant_id: str
    metric_name: str
    metric_display_name: str
    alert_type: str  # "drop" or "spike"
    severity: AlertSeverity
    status: AlertStatus

    # Values
    current_value: float
    baseline_value: float  # Median
    z_score: float
    percentage_change: float

    # Context
    date: str  # Date the anomaly occurred
    created_at: datetime
    updated_at: datetime

    # Additional context
    unit: str = "count"
    message: str = ""
    historical_values: list[float] = field(default_factory=list)

    # Tracking
    acknowledged_at: Optional[datetime] = None
    acknowledged_by: Optional[str] = None
    resolved_at: Optional[datetime] = None
    notes: Optional[str] = None

    def to_dict(self) -> dict:
        """Convert to dictionary for API response."""
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "metric_name": self.metric_name,
            "metric_display_name": self.metric_display_name,
            "alert_type": self.alert_type,
            "severity": self.severity.value,
            "status": self.status.value,
            "current_value": self.current_value,
            "baseline_value": self.baseline_value,
            "z_score": round(self.z_score, 2),
            "percentage_change": round(self.percentage_change, 1),
            "date": self.date,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "unit": self.unit,
            "message": self.message,
            "historical_values": self.historical_values,
            "acknowledged_at": self.acknowledged_at.isoformat() if self.acknowledged_at else None,
            "acknowledged_by": self.acknowledged_by,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            "notes": self.notes,
        }


def generate_alert_message(
    metric_display_name: str,
    alert_type: str,
    percentage_change: float,
    current_value: float,
    baseline_value: float,
    unit: str,
) -> str:
    """Generate a human-readable alert message."""
    direction = "dropped" if alert_type == "drop" else "spiked"
    change_str = f"{abs(percentage_change):.1f}%"

    if unit == "currency":
        current_str = f"${current_value:,.2f}"
        baseline_str = f"${baseline_value:,.2f}"
    else:
        current_str = f"{current_value:,.0f}"
        baseline_str = f"{baseline_value:,.0f}"

    return (
        f"{metric_display_name} {direction} by {change_str}. "
        f"Current: {current_str}, Normal: {baseline_str}"
    )
