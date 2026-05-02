"""ClickHouse repository for metric data."""

from datetime import date, timedelta
from typing import Optional
import logging

import clickhouse_connect

from ..core.metrics import MetricDefinition

logger = logging.getLogger(__name__)


class MetricRepository:
    """Repository for fetching metric values from ClickHouse."""

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

    def get_metric_value(
        self,
        metric: MetricDefinition,
        tenant_id: str,
        target_date: date,
    ) -> float:
        """
        Get the metric value for a specific tenant and date.

        Args:
            metric: Metric definition with query template
            tenant_id: Tenant ID
            target_date: Date to query

        Returns:
            Metric value (0 if no data)
        """
        query = metric.query_template.format(
            tenant_id=tenant_id,
            date=target_date.isoformat(),
        )

        try:
            result = self.client.query(query)
            if result.result_rows:
                return float(result.result_rows[0][0] or 0)
            return 0.0
        except Exception as e:
            logger.error(f"Failed to query metric {metric.name} for {tenant_id}: {e}")
            return 0.0

    def get_historical_values(
        self,
        metric: MetricDefinition,
        tenant_id: str,
        target_date: date,
        weeks: int = 8,
    ) -> list[float]:
        """
        Get same-day-of-week values for past N weeks.

        Args:
            metric: Metric definition
            tenant_id: Tenant ID
            target_date: Reference date (typically yesterday)
            weeks: Number of weeks of history to fetch

        Returns:
            List of values, most recent first
        """
        values = []

        for week_offset in range(1, weeks + 1):
            historical_date = target_date - timedelta(weeks=week_offset)
            value = self.get_metric_value(metric, tenant_id, historical_date)
            values.append(value)

        return values

    def get_metric_with_baseline(
        self,
        metric: MetricDefinition,
        tenant_id: str,
        target_date: date,
        baseline_weeks: int = 8,
    ) -> tuple[float, list[float]]:
        """
        Get current value and historical baseline in one call.

        Args:
            metric: Metric definition
            tenant_id: Tenant ID
            target_date: Date to analyze
            baseline_weeks: Weeks of history for baseline

        Returns:
            Tuple of (current_value, historical_values)
        """
        current = self.get_metric_value(metric, tenant_id, target_date)
        historical = self.get_historical_values(
            metric, tenant_id, target_date, baseline_weeks
        )
        return current, historical

    def get_active_tenants(self) -> list[str]:
        """
        Get list of active tenant IDs.

        Returns tenants that have had activity in the past 30 days.
        """
        query = """
            SELECT DISTINCT tenantId
            FROM TWCWISHLIST_ITEM
            WHERE createdAt >= now() - INTERVAL 30 DAY
            ORDER BY tenantId
        """

        try:
            result = self.client.query(query)
            return [row[0] for row in result.result_rows]
        except Exception as e:
            logger.error(f"Failed to get active tenants: {e}")
            return []

    def get_all_metrics_for_date(
        self,
        metrics: list[MetricDefinition],
        target_date: date,
        baseline_weeks: int = 8,
    ) -> list[dict]:
        """
        Efficiently fetch all metrics for all tenants for a given date.

        Returns list of dicts with tenant_id, metric_name, current_value, historical_values.
        """
        tenants = self.get_active_tenants()
        results = []

        for tenant_id in tenants:
            for metric in metrics:
                current, historical = self.get_metric_with_baseline(
                    metric, tenant_id, target_date, baseline_weeks
                )
                results.append({
                    "tenant_id": tenant_id,
                    "metric_name": metric.name,
                    "current_value": current,
                    "historical_values": historical,
                })

        return results
