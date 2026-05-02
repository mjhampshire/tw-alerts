"""Alert storage repository using ClickHouse."""

from datetime import datetime, timedelta
from typing import Optional
import uuid
import logging

import clickhouse_connect

from .models import Alert, AlertStatus, AlertSeverity

logger = logging.getLogger(__name__)


class AlertRepository:
    """Repository for storing and retrieving alerts."""

    def __init__(
        self,
        host: str,
        port: int = 8123,
        username: str = "default",
        password: str = "",
        database: str = "default",
    ):
        self.client = clickhouse_connect.get_client(
            host=host,
            port=port,
            username=username,
            password=password,
            database=database,
        )

    def create_table(self) -> None:
        """Create the alerts table if it doesn't exist."""
        query = """
            CREATE TABLE IF NOT EXISTS TWCALERT (
                id String,
                tenantId String,
                metricName String,
                metricDisplayName String,
                alertType String,
                severity String,
                status String,
                currentValue Float64,
                baselineValue Float64,
                zScore Float64,
                percentageChange Float64,
                alertDate Date,
                unit String,
                message String,
                historicalValues Array(Float64),
                createdAt DateTime DEFAULT now(),
                updatedAt DateTime DEFAULT now(),
                acknowledgedAt Nullable(DateTime),
                acknowledgedBy Nullable(String),
                resolvedAt Nullable(DateTime),
                notes Nullable(String)
            ) ENGINE = ReplacingMergeTree(updatedAt)
            ORDER BY (tenantId, alertDate, metricName, id)
        """
        self.client.command(query)

    def save_alert(self, alert: Alert) -> str:
        """
        Save a new alert or update existing one.

        Returns the alert ID.
        """
        self.client.insert(
            "TWCALERT",
            [[
                alert.id,
                alert.tenant_id,
                alert.metric_name,
                alert.metric_display_name,
                alert.alert_type,
                alert.severity.value,
                alert.status.value,
                alert.current_value,
                alert.baseline_value,
                alert.z_score,
                alert.percentage_change,
                alert.date,
                alert.unit,
                alert.message,
                alert.historical_values,
                alert.created_at,
                alert.updated_at,
                alert.acknowledged_at,
                alert.acknowledged_by,
                alert.resolved_at,
                alert.notes,
            ]],
            column_names=[
                "id", "tenantId", "metricName", "metricDisplayName",
                "alertType", "severity", "status", "currentValue",
                "baselineValue", "zScore", "percentageChange", "alertDate",
                "unit", "message", "historicalValues", "createdAt",
                "updatedAt", "acknowledgedAt", "acknowledgedBy",
                "resolvedAt", "notes",
            ],
        )
        return alert.id

    def get_alert(self, alert_id: str) -> Optional[Alert]:
        """Get a single alert by ID."""
        query = f"""
            SELECT *
            FROM TWCALERT
            WHERE id = '{alert_id}'
            ORDER BY updatedAt DESC
            LIMIT 1
        """
        result = self.client.query(query)
        if result.result_rows:
            return self._row_to_alert(result.result_rows[0])
        return None

    def get_alerts_for_tenant(
        self,
        tenant_id: str,
        status: Optional[AlertStatus] = None,
        days: int = 30,
        limit: int = 100,
    ) -> list[Alert]:
        """Get alerts for a tenant, optionally filtered by status."""
        status_filter = f"AND status = '{status.value}'" if status else ""
        query = f"""
            SELECT *
            FROM TWCALERT
            WHERE tenantId = '{tenant_id}'
              AND alertDate >= today() - INTERVAL {days} DAY
              {status_filter}
            ORDER BY createdAt DESC
            LIMIT {limit}
        """
        result = self.client.query(query)
        return [self._row_to_alert(row) for row in result.result_rows]

    def get_active_alerts(self, tenant_id: str) -> list[Alert]:
        """Get all active (unacknowledged) alerts for a tenant."""
        return self.get_alerts_for_tenant(tenant_id, status=AlertStatus.ACTIVE)

    def check_duplicate(
        self,
        tenant_id: str,
        metric_name: str,
        alert_type: str,
        days: int = 3,
    ) -> bool:
        """
        Check if a similar alert was already fired recently.

        Used for deduplication - don't fire same alert multiple days in a row.
        """
        query = f"""
            SELECT count(*) as cnt
            FROM TWCALERT
            WHERE tenantId = '{tenant_id}'
              AND metricName = '{metric_name}'
              AND alertType = '{alert_type}'
              AND status IN ('active', 'acknowledged')
              AND alertDate >= today() - INTERVAL {days} DAY
        """
        result = self.client.query(query)
        count = result.result_rows[0][0] if result.result_rows else 0
        return count > 0

    def update_status(
        self,
        alert_id: str,
        status: AlertStatus,
        acknowledged_by: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> bool:
        """Update alert status."""
        alert = self.get_alert(alert_id)
        if not alert:
            return False

        alert.status = status
        alert.updated_at = datetime.now()

        if status == AlertStatus.ACKNOWLEDGED:
            alert.acknowledged_at = datetime.now()
            alert.acknowledged_by = acknowledged_by
        elif status == AlertStatus.RESOLVED:
            alert.resolved_at = datetime.now()

        if notes:
            alert.notes = notes

        self.save_alert(alert)
        return True

    def _row_to_alert(self, row: tuple) -> Alert:
        """Convert a database row to Alert model."""
        return Alert(
            id=row[0],
            tenant_id=row[1],
            metric_name=row[2],
            metric_display_name=row[3],
            alert_type=row[4],
            severity=AlertSeverity(row[5]),
            status=AlertStatus(row[6]),
            current_value=row[7],
            baseline_value=row[8],
            z_score=row[9],
            percentage_change=row[10],
            date=str(row[11]),
            unit=row[12],
            message=row[13],
            historical_values=list(row[14]) if row[14] else [],
            created_at=row[15],
            updated_at=row[16],
            acknowledged_at=row[17],
            acknowledged_by=row[18],
            resolved_at=row[19],
            notes=row[20],
        )
