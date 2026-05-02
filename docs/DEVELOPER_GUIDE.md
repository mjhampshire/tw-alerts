# Developer Guide

## Architecture Overview

```
src/
├── api/
│   ├── app.py          # FastAPI application entry point
│   └── routes.py       # API endpoint definitions
├── alerts/
│   ├── models.py       # Alert, AlertStatus, AlertSeverity dataclasses
│   ├── repository.py   # ClickHouse CRUD operations for alerts
│   └── notifier.py     # Webhook, Email, Slack notification services
├── core/
│   ├── anomaly.py      # Anomaly detection algorithm
│   └── metrics.py      # Metric definitions
├── data/
│   └── repository.py   # ClickHouse queries for metric values
└── jobs/
    └── detect_anomalies.py  # CRON job entry point
```

## Adding a New Metric

### 1. Define the Metric

Edit `src/core/metrics.py`:

```python
METRICS = {
    # ... existing metrics ...

    "cart_abandonment_rate": MetricDefinition(
        name="cart_abandonment_rate",
        display_name="Cart Abandonment Rate",
        description="Percentage of carts abandoned",
        table="TWCCART_EVENTS",
        value_column="abandonment_rate",
        date_column="event_date",
        tenant_column="tenantId",
        aggregation="avg",  # Use average for rates
        unit="percent",
        drop_threshold=-2.0,   # More sensitive for rates
        spike_threshold=2.5,
        min_volume=100,        # Minimum cart events
        min_history_weeks=4,
    ),
}
```

### 2. Metric Definition Fields

| Field | Description |
|-------|-------------|
| `name` | Unique identifier (snake_case) |
| `display_name` | Human-readable name |
| `table` | ClickHouse table name |
| `value_column` | Column containing the metric value |
| `date_column` | Column containing the date |
| `tenant_column` | Column containing tenant ID |
| `aggregation` | How to aggregate: `sum`, `avg`, `count`, `max` |
| `unit` | Display unit: `count`, `currency`, `percent` |
| `drop_threshold` | Z-score threshold for drop alerts (negative) |
| `spike_threshold` | Z-score threshold for spike alerts (positive) |
| `min_volume` | Minimum value to consider (filters low-traffic) |
| `min_history_weeks` | Weeks of data needed before alerting |

### 3. Custom Queries

For complex metrics, override the query in `src/data/repository.py`:

```python
def get_metric_value(
    self,
    metric: MetricDefinition,
    tenant_id: str,
    target_date: date,
) -> float:
    # Custom logic for specific metrics
    if metric.name == "cart_abandonment_rate":
        return self._get_cart_abandonment_rate(tenant_id, target_date)

    # Default query
    return self._execute_metric_query(metric, tenant_id, target_date)

def _get_cart_abandonment_rate(self, tenant_id: str, target_date: date) -> float:
    query = f"""
        SELECT
            countIf(status = 'abandoned') / count(*) * 100 as rate
        FROM TWCCART_EVENTS
        WHERE tenantId = '{tenant_id}'
          AND toDate(event_date) = '{target_date}'
    """
    result = self.client.query(query)
    return result.result_rows[0][0] if result.result_rows else 0.0
```

## Anomaly Detection Algorithm

### Overview

The system uses **Median + MAD (Median Absolute Deviation)** which is robust to outliers.

### Why Median + MAD?

Traditional mean + standard deviation can be skewed by outliers:

```
Normal week:    [100, 105, 98, 102, 100, 103, 99]
Black Friday:   [100, 105, 98, 102, 100, 103, 500]  # 500 is outlier

Mean + StdDev: Mean shifts from 101 to 158, making future drops look normal
Median + MAD:  Median stays at 102, outlier doesn't affect baseline
```

### Baseline Calculation

```python
def compute_baseline(historical_values: list[float]) -> BaselineStats:
    values = sorted(historical_values)
    n = len(values)

    # Median
    if n % 2 == 0:
        median = (values[n//2 - 1] + values[n//2]) / 2
    else:
        median = values[n//2]

    # MAD (Median Absolute Deviation)
    deviations = sorted([abs(v - median) for v in values])
    if n % 2 == 0:
        mad = (deviations[n//2 - 1] + deviations[n//2]) / 2
    else:
        mad = deviations[n//2]

    # Scale MAD to approximate standard deviation
    scaled_mad = mad * 1.4826

    return BaselineStats(median=median, mad=mad, scaled_mad=scaled_mad)
```

### Z-Score Calculation

```python
def compute_z_score(current: float, baseline: BaselineStats) -> float:
    if baseline.scaled_mad == 0:
        # Handle zero variance (all historical values identical)
        if current == baseline.median:
            return 0.0
        return 5.0 if current > baseline.median else -5.0

    return (current - baseline.median) / baseline.scaled_mad
```

### Threshold Application

```python
def is_anomaly(z_score: float, drop_threshold: float, spike_threshold: float) -> tuple[bool, str]:
    if z_score < drop_threshold:
        return True, "drop"
    if z_score > spike_threshold:
        return True, "spike"
    return False, None
```

## Adding a Notification Channel

### 1. Create Notifier Class

Edit `src/alerts/notifier.py`:

```python
class PagerDutyNotifier(Notifier):
    """Send alerts to PagerDuty."""

    def __init__(self, routing_key: str):
        self.routing_key = routing_key
        self.api_url = "https://events.pagerduty.com/v2/enqueue"

    async def send(self, alert: Alert, service_key: str) -> bool:
        payload = {
            "routing_key": service_key or self.routing_key,
            "event_action": "trigger",
            "dedup_key": alert.id,
            "payload": {
                "summary": alert.message,
                "severity": self._map_severity(alert.severity),
                "source": f"twc-alerts:{alert.tenant_id}",
                "custom_details": alert.to_dict(),
            },
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(self.api_url, json=payload)
                response.raise_for_status()
                return True
        except Exception as e:
            logger.error(f"Failed to send PagerDuty alert: {e}")
            return False

    def _map_severity(self, severity: AlertSeverity) -> str:
        mapping = {
            AlertSeverity.CRITICAL: "critical",
            AlertSeverity.HIGH: "error",
            AlertSeverity.MEDIUM: "warning",
            AlertSeverity.LOW: "info",
        }
        return mapping.get(severity, "info")
```

### 2. Register in Detection Job

Edit `src/jobs/detect_anomalies.py`:

```python
class AnomalyDetectionJob:
    def __init__(self, ...):
        # ... existing notifiers ...
        self.pagerduty_notifier = PagerDutyNotifier(
            routing_key=os.getenv("PAGERDUTY_ROUTING_KEY", "")
        )

    async def _send_notifications(self, alert: Alert, tenant_id: str) -> None:
        # ... existing notification logic ...

        # PagerDuty for critical alerts
        if alert.severity == AlertSeverity.CRITICAL:
            pd_key = os.getenv(f"PAGERDUTY_KEY_{tenant_id.upper()}")
            if pd_key:
                await self.pagerduty_notifier.send(alert, pd_key)
```

## Customizing Thresholds Per Tenant

For tenant-specific thresholds, modify `src/core/metrics.py`:

```python
# Tenant-specific overrides
TENANT_THRESHOLDS = {
    "high-volume-tenant": {
        "revenue_generated": {"drop_threshold": -1.5, "spike_threshold": 3.0},
    },
    "low-volume-tenant": {
        "wishlist_items_notify_me": {"min_volume": 10},
    },
}

def get_metric(name: str, tenant_id: str = None) -> MetricDefinition:
    metric = METRICS.get(name)
    if not metric:
        return None

    # Apply tenant overrides
    if tenant_id and tenant_id in TENANT_THRESHOLDS:
        overrides = TENANT_THRESHOLDS[tenant_id].get(name, {})
        if overrides:
            metric = MetricDefinition(**{**metric.__dict__, **overrides})

    return metric
```

## Testing

### Unit Tests

```python
# tests/test_anomaly.py
import pytest
from src.core.anomaly import compute_baseline, compute_z_score, detect_anomaly

def test_baseline_calculation():
    values = [100, 105, 98, 102, 100, 103, 99]
    baseline = compute_baseline(values)

    assert baseline.median == 100
    assert baseline.mad == 2
    assert baseline.scaled_mad == pytest.approx(2.965, rel=0.01)

def test_z_score_normal():
    baseline = BaselineStats(median=100, mad=2, scaled_mad=2.965)
    z = compute_z_score(100, baseline)
    assert z == 0.0

def test_z_score_drop():
    baseline = BaselineStats(median=100, mad=2, scaled_mad=2.965)
    z = compute_z_score(50, baseline)
    assert z < -2.5  # Should trigger drop alert

def test_anomaly_detection_drop():
    result = detect_anomaly(
        metric_name="test",
        tenant_id="test",
        date="2024-01-15",
        current_value=50,
        historical_values=[100, 105, 98, 102, 100, 103, 99, 101],
        drop_threshold=-2.5,
        spike_threshold=3.5,
    )

    assert result.is_anomaly
    assert result.anomaly_type == "drop"
```

### Integration Tests

```python
# tests/test_integration.py
import pytest
from src.jobs.detect_anomalies import AnomalyDetectionJob

@pytest.fixture
def mock_repos(mocker):
    metric_repo = mocker.Mock()
    alert_repo = mocker.Mock()

    metric_repo.get_active_tenants.return_value = ["test-tenant"]
    metric_repo.get_metric_with_baseline.return_value = (
        50.0,  # Current value (low)
        [100, 105, 98, 102, 100, 103, 99, 101],  # Historical
    )
    alert_repo.check_duplicate.return_value = False

    return metric_repo, alert_repo

async def test_job_creates_alert(mock_repos):
    metric_repo, alert_repo = mock_repos

    job = AnomalyDetectionJob(metric_repo, alert_repo)
    alerts = await job.run()

    assert len(alerts) > 0
    assert alert_repo.save_alert.called
```

## Debugging

### Enable Debug Logging

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

### Check Raw Values

```python
from src.data.repository import MetricRepository
from src.core.metrics import get_metric
from datetime import date

repo = MetricRepository(host="localhost")
metric = get_metric("revenue_generated")

current, historical = repo.get_metric_with_baseline(
    metric,
    "your-tenant",
    date.today(),
    baseline_weeks=8
)

print(f"Current: {current}")
print(f"Historical: {historical}")
print(f"Median: {sorted(historical)[len(historical)//2]}")
```

### Simulate Detection

```python
from src.core.anomaly import detect_anomaly

result = detect_anomaly(
    metric_name="revenue_generated",
    tenant_id="test",
    date="2024-01-15",
    current_value=1000,
    historical_values=[3000, 3100, 2900, 3050, 3000, 2950, 3000, 3100],
    drop_threshold=-2.5,
    spike_threshold=3.5,
)

print(f"Is anomaly: {result.is_anomaly}")
print(f"Type: {result.anomaly_type}")
print(f"Z-score: {result.z_score}")
print(f"Percentage change: {result.percentage_change}%")
```
