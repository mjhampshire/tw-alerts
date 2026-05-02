"""Anomaly detection using median + MAD (Median Absolute Deviation).

This approach is robust to outliers like Black Friday spikes contaminating
the baseline. We use the same-day-of-week values over past N weeks.

Z-score calculation:
    z = (today - median) / (MAD * 1.4826)

Where 1.4826 scales MAD to approximate standard deviation for normal distributions.
"""

from dataclasses import dataclass
from typing import Optional
from statistics import median
import math


# Scale factor to convert MAD to approximate standard deviation
MAD_SCALE_FACTOR = 1.4826


@dataclass
class BaselineStats:
    """Baseline statistics for a metric."""
    median: float
    mad: float  # Median Absolute Deviation
    values: list[float]  # Historical values used
    weeks_of_data: int

    @property
    def scaled_mad(self) -> float:
        """MAD scaled to approximate standard deviation."""
        return self.mad * MAD_SCALE_FACTOR

    @property
    def has_sufficient_data(self) -> bool:
        """Check if we have enough data points."""
        return self.weeks_of_data >= 4


@dataclass
class AnomalyResult:
    """Result of anomaly detection for a single metric."""
    metric_name: str
    tenant_id: str
    date: str
    current_value: float
    baseline: BaselineStats
    z_score: float
    is_anomaly: bool
    anomaly_type: Optional[str]  # "drop", "spike", or None
    percentage_change: float

    @property
    def severity(self) -> str:
        """Classify severity based on z-score magnitude."""
        abs_z = abs(self.z_score)
        if abs_z >= 5:
            return "critical"
        elif abs_z >= 4:
            return "high"
        elif abs_z >= 3:
            return "medium"
        else:
            return "low"


def compute_mad(values: list[float]) -> float:
    """Compute Median Absolute Deviation."""
    if not values:
        return 0.0
    med = median(values)
    deviations = [abs(v - med) for v in values]
    return median(deviations) if deviations else 0.0


def compute_baseline(values: list[float]) -> BaselineStats:
    """
    Compute baseline statistics from historical values.

    Args:
        values: List of same-day-of-week values (most recent first)

    Returns:
        BaselineStats with median, MAD, and metadata
    """
    if not values:
        return BaselineStats(
            median=0.0,
            mad=0.0,
            values=[],
            weeks_of_data=0,
        )

    med = median(values)
    mad = compute_mad(values)

    return BaselineStats(
        median=med,
        mad=mad,
        values=values,
        weeks_of_data=len(values),
    )


def compute_z_score(current: float, baseline: BaselineStats) -> float:
    """
    Compute z-score of current value against baseline.

    Uses scaled MAD instead of standard deviation for robustness.
    Returns 0 if baseline has no variance (all same values).
    """
    if baseline.scaled_mad == 0:
        # No variance - can't compute meaningful z-score
        # Return 0 if current matches baseline, else a large value
        if current == baseline.median:
            return 0.0
        # Use a default "large" z-score for significant deviation
        return 5.0 if current > baseline.median else -5.0

    return (current - baseline.median) / baseline.scaled_mad


def detect_anomaly(
    metric_name: str,
    tenant_id: str,
    date: str,
    current_value: float,
    historical_values: list[float],
    drop_threshold: float = -2.5,
    spike_threshold: float = 3.5,
    min_volume: int = 5,
    min_history_weeks: int = 4,
) -> AnomalyResult:
    """
    Detect if current value is anomalous compared to historical baseline.

    Args:
        metric_name: Name of the metric
        tenant_id: Tenant/customer ID
        date: Date being analyzed
        current_value: Today's metric value
        historical_values: Same-day-of-week values from past weeks
        drop_threshold: Z-score threshold for drops (negative value)
        spike_threshold: Z-score threshold for spikes (positive value)
        min_volume: Minimum absolute value to consider alerting
        min_history_weeks: Minimum weeks of history required

    Returns:
        AnomalyResult with detection details
    """
    baseline = compute_baseline(historical_values)
    z_score = compute_z_score(current_value, baseline)

    # Calculate percentage change from baseline
    if baseline.median > 0:
        percentage_change = ((current_value - baseline.median) / baseline.median) * 100
    elif current_value > 0:
        percentage_change = 100.0  # Went from 0 to something
    else:
        percentage_change = 0.0

    # Determine if this is an anomaly
    is_anomaly = False
    anomaly_type = None

    # Check guards first
    if baseline.weeks_of_data < min_history_weeks:
        # Not enough history
        pass
    elif current_value < min_volume and baseline.median < min_volume:
        # Low volume - don't alert on noise
        pass
    elif z_score <= drop_threshold:
        is_anomaly = True
        anomaly_type = "drop"
    elif z_score >= spike_threshold:
        is_anomaly = True
        anomaly_type = "spike"

    return AnomalyResult(
        metric_name=metric_name,
        tenant_id=tenant_id,
        date=date,
        current_value=current_value,
        baseline=baseline,
        z_score=z_score,
        is_anomaly=is_anomaly,
        anomaly_type=anomaly_type,
        percentage_change=percentage_change,
    )
