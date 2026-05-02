"""CRON job for detecting anomalies and generating alerts.

Run daily after data is settled (e.g., 6 AM):
    python -m src.jobs.detect_anomalies

Or via crontab:
    0 6 * * * /path/to/python -m src.jobs.detect_anomalies
"""

import os
import asyncio
import uuid
from datetime import date, datetime, timedelta
from typing import Optional
import logging

from ..core.metrics import get_all_metrics, MetricDefinition
from ..core.anomaly import detect_anomaly, AnomalyResult
from ..data.repository import MetricRepository
from ..alerts.models import Alert, AlertStatus, AlertSeverity, generate_alert_message
from ..alerts.repository import AlertRepository
from ..alerts.notifier import WebhookNotifier, EmailNotifier, SlackNotifier

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class AnomalyDetectionJob:
    """Job to detect anomalies and create alerts."""

    def __init__(
        self,
        metric_repo: MetricRepository,
        alert_repo: AlertRepository,
        baseline_weeks: int = 8,
        dedup_days: int = 3,
    ):
        self.metric_repo = metric_repo
        self.alert_repo = alert_repo
        self.baseline_weeks = baseline_weeks
        self.dedup_days = dedup_days

        # Notifiers (configured via env vars)
        self.webhook_notifier = WebhookNotifier()
        self.slack_notifier = SlackNotifier()

    async def run(self, target_date: Optional[date] = None) -> list[Alert]:
        """
        Run anomaly detection for all tenants and metrics.

        Args:
            target_date: Date to analyze (defaults to yesterday)

        Returns:
            List of alerts generated
        """
        if target_date is None:
            target_date = date.today() - timedelta(days=1)

        logger.info(f"Running anomaly detection for {target_date}")

        metrics = get_all_metrics()
        tenants = self.metric_repo.get_active_tenants()

        logger.info(f"Checking {len(metrics)} metrics for {len(tenants)} tenants")

        alerts_generated = []

        for tenant_id in tenants:
            tenant_alerts = await self._process_tenant(tenant_id, metrics, target_date)
            alerts_generated.extend(tenant_alerts)

        logger.info(f"Generated {len(alerts_generated)} alerts")
        return alerts_generated

    async def _process_tenant(
        self,
        tenant_id: str,
        metrics: list[MetricDefinition],
        target_date: date,
    ) -> list[Alert]:
        """Process all metrics for a single tenant."""
        alerts = []

        for metric in metrics:
            try:
                alert = await self._check_metric(tenant_id, metric, target_date)
                if alert:
                    alerts.append(alert)
            except Exception as e:
                logger.error(f"Error checking {metric.name} for {tenant_id}: {e}")

        return alerts

    async def _check_metric(
        self,
        tenant_id: str,
        metric: MetricDefinition,
        target_date: date,
    ) -> Optional[Alert]:
        """Check a single metric for anomalies."""
        # Get current value and historical baseline
        current, historical = self.metric_repo.get_metric_with_baseline(
            metric, tenant_id, target_date, self.baseline_weeks
        )

        # Run anomaly detection
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

        if not result.is_anomaly:
            return None

        # Check for duplicate (don't fire same alert multiple days)
        if self.alert_repo.check_duplicate(
            tenant_id, metric.name, result.anomaly_type, self.dedup_days
        ):
            logger.info(
                f"Skipping duplicate alert: {metric.name} {result.anomaly_type} "
                f"for {tenant_id}"
            )
            return None

        # Create alert
        alert = self._create_alert(result, metric)

        # Save to database
        self.alert_repo.save_alert(alert)
        logger.info(f"Created alert: {alert.id} - {alert.message}")

        # Send notifications
        await self._send_notifications(alert, tenant_id)

        return alert

    def _create_alert(
        self,
        result: AnomalyResult,
        metric: MetricDefinition,
    ) -> Alert:
        """Create an Alert from an AnomalyResult."""
        message = generate_alert_message(
            metric_display_name=metric.display_name,
            alert_type=result.anomaly_type,
            percentage_change=result.percentage_change,
            current_value=result.current_value,
            baseline_value=result.baseline.median,
            unit=metric.unit,
        )

        return Alert(
            id=str(uuid.uuid4()),
            tenant_id=result.tenant_id,
            metric_name=result.metric_name,
            metric_display_name=metric.display_name,
            alert_type=result.anomaly_type,
            severity=AlertSeverity(result.severity),
            status=AlertStatus.ACTIVE,
            current_value=result.current_value,
            baseline_value=result.baseline.median,
            z_score=result.z_score,
            percentage_change=result.percentage_change,
            date=result.date,
            created_at=datetime.now(),
            updated_at=datetime.now(),
            unit=metric.unit,
            message=message,
            historical_values=result.baseline.values,
        )

    async def _send_notifications(self, alert: Alert, tenant_id: str) -> None:
        """Send alert notifications based on tenant config."""
        # TODO: Look up tenant notification preferences from database
        # For now, check environment variables for global config

        webhook_url = os.getenv(f"ALERT_WEBHOOK_{tenant_id.upper()}")
        if not webhook_url:
            webhook_url = os.getenv("ALERT_WEBHOOK_DEFAULT")

        if webhook_url:
            await self.webhook_notifier.send(alert, webhook_url)

        slack_url = os.getenv(f"ALERT_SLACK_{tenant_id.upper()}")
        if not slack_url:
            slack_url = os.getenv("ALERT_SLACK_DEFAULT")

        if slack_url:
            await self.slack_notifier.send(alert, slack_url)


def get_config_from_env() -> dict:
    """Get ClickHouse config from environment variables."""
    return {
        "host": os.getenv("CLICKHOUSE_HOST", "localhost"),
        "port": int(os.getenv("CLICKHOUSE_PORT", "8123")),
        "username": os.getenv("CLICKHOUSE_USER", "default"),
        "password": os.getenv("CLICKHOUSE_PASSWORD", ""),
        "database": os.getenv("CLICKHOUSE_DATABASE", "default"),
    }


async def main():
    """Entry point for the anomaly detection job."""
    config = get_config_from_env()

    metric_repo = MetricRepository(**config)
    alert_repo = AlertRepository(**config)

    # Ensure table exists
    alert_repo.create_table()

    job = AnomalyDetectionJob(metric_repo, alert_repo)
    alerts = await job.run()

    print(f"Anomaly detection complete. Generated {len(alerts)} alerts.")
    for alert in alerts:
        print(f"  - {alert.tenant_id}: {alert.message}")


if __name__ == "__main__":
    asyncio.run(main())
