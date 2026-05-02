"""Trend analysis for metrics.

Calculates whether a metric is trending up, down, or stable over time.
Different from anomaly detection - this is about general direction, not unusual spikes/drops.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional
import statistics


class TrendDirection(Enum):
    """Direction of the trend."""
    UP = "up"
    DOWN = "down"
    STABLE = "stable"
    INSUFFICIENT_DATA = "insufficient_data"


@dataclass
class TrendResult:
    """Result of trend analysis."""
    metric_name: str
    tenant_id: str
    direction: TrendDirection
    percentage_change: float  # Change from prior to recent period
    recent_average: float
    prior_average: float
    confidence: str  # "high", "medium", "low"
    recent_period_days: int
    prior_period_days: int
    description: str  # Human-readable summary

    def to_dict(self) -> dict:
        return {
            "metric_name": self.metric_name,
            "tenant_id": self.tenant_id,
            "direction": self.direction.value,
            "percentage_change": round(self.percentage_change, 1),
            "recent_average": round(self.recent_average, 2),
            "prior_average": round(self.prior_average, 2),
            "confidence": self.confidence,
            "recent_period_days": self.recent_period_days,
            "prior_period_days": self.prior_period_days,
            "description": self.description,
        }


def calculate_trend(
    metric_name: str,
    tenant_id: str,
    recent_values: list[float],
    prior_values: list[float],
    up_threshold: float = 5.0,  # % change to consider "up"
    down_threshold: float = -5.0,  # % change to consider "down"
) -> TrendResult:
    """
    Calculate trend by comparing recent period to prior period.

    Args:
        metric_name: Name of the metric
        tenant_id: Tenant identifier
        recent_values: Values from recent period (e.g., last 7 days)
        prior_values: Values from prior period (e.g., 7 days before that)
        up_threshold: Minimum % increase to consider trending up
        down_threshold: Maximum % decrease to consider trending down

    Returns:
        TrendResult with direction and details
    """
    # Check for sufficient data
    if len(recent_values) < 3 or len(prior_values) < 3:
        return TrendResult(
            metric_name=metric_name,
            tenant_id=tenant_id,
            direction=TrendDirection.INSUFFICIENT_DATA,
            percentage_change=0.0,
            recent_average=0.0,
            prior_average=0.0,
            confidence="low",
            recent_period_days=len(recent_values),
            prior_period_days=len(prior_values),
            description="Insufficient data for trend analysis",
        )

    recent_avg = statistics.mean(recent_values)
    prior_avg = statistics.mean(prior_values)

    # Calculate percentage change
    if prior_avg == 0:
        if recent_avg == 0:
            percentage_change = 0.0
        else:
            percentage_change = 100.0  # From zero to something
    else:
        percentage_change = ((recent_avg - prior_avg) / prior_avg) * 100

    # Determine direction
    if percentage_change >= up_threshold:
        direction = TrendDirection.UP
    elif percentage_change <= down_threshold:
        direction = TrendDirection.DOWN
    else:
        direction = TrendDirection.STABLE

    # Calculate confidence based on consistency
    confidence = _calculate_confidence(recent_values, prior_values, direction)

    # Generate description
    description = _generate_description(
        direction, percentage_change, recent_avg, prior_avg
    )

    return TrendResult(
        metric_name=metric_name,
        tenant_id=tenant_id,
        direction=direction,
        percentage_change=percentage_change,
        recent_average=recent_avg,
        prior_average=prior_avg,
        confidence=confidence,
        recent_period_days=len(recent_values),
        prior_period_days=len(prior_values),
        description=description,
    )


def _calculate_confidence(
    recent_values: list[float],
    prior_values: list[float],
    direction: TrendDirection,
) -> str:
    """
    Calculate confidence based on consistency of the trend.

    High confidence: Low variance, consistent direction
    Medium confidence: Some variance but clear direction
    Low confidence: High variance or mixed signals
    """
    if direction == TrendDirection.STABLE:
        return "high"  # Stable is easy to be confident about

    # Check coefficient of variation (CV) for both periods
    try:
        recent_cv = statistics.stdev(recent_values) / statistics.mean(recent_values) if statistics.mean(recent_values) != 0 else 0
        prior_cv = statistics.stdev(prior_values) / statistics.mean(prior_values) if statistics.mean(prior_values) != 0 else 0
    except statistics.StatisticsError:
        return "low"

    avg_cv = (recent_cv + prior_cv) / 2

    # Check if recent period shows consistent direction
    if direction == TrendDirection.UP:
        recent_trend_consistent = sum(1 for i in range(1, len(recent_values)) if recent_values[i] >= recent_values[i-1])
    else:
        recent_trend_consistent = sum(1 for i in range(1, len(recent_values)) if recent_values[i] <= recent_values[i-1])

    consistency_ratio = recent_trend_consistent / (len(recent_values) - 1) if len(recent_values) > 1 else 0

    # High confidence: low variance AND consistent direction
    if avg_cv < 0.2 and consistency_ratio >= 0.6:
        return "high"
    # Low confidence: high variance OR inconsistent
    elif avg_cv > 0.5 or consistency_ratio < 0.4:
        return "low"
    else:
        return "medium"


def _generate_description(
    direction: TrendDirection,
    percentage_change: float,
    recent_avg: float,
    prior_avg: float,
) -> str:
    """Generate a human-readable trend description."""
    if direction == TrendDirection.STABLE:
        return f"Stable at ~{recent_avg:,.0f} (no significant change)"

    if direction == TrendDirection.UP:
        return f"Trending up {percentage_change:+.1f}% ({prior_avg:,.0f} → {recent_avg:,.0f})"

    if direction == TrendDirection.DOWN:
        return f"Trending down {percentage_change:.1f}% ({prior_avg:,.0f} → {recent_avg:,.0f})"

    return "Unable to determine trend"


def calculate_trend_with_slope(
    metric_name: str,
    tenant_id: str,
    daily_values: list[float],
    min_days: int = 7,
) -> TrendResult:
    """
    Alternative trend calculation using linear regression slope.

    Better for detecting gradual trends over longer periods.
    Uses simple linear regression to find the slope.
    """
    if len(daily_values) < min_days:
        return TrendResult(
            metric_name=metric_name,
            tenant_id=tenant_id,
            direction=TrendDirection.INSUFFICIENT_DATA,
            percentage_change=0.0,
            recent_average=0.0,
            prior_average=0.0,
            confidence="low",
            recent_period_days=len(daily_values),
            prior_period_days=0,
            description="Insufficient data for trend analysis",
        )

    n = len(daily_values)
    x = list(range(n))  # Day indices: 0, 1, 2, ...

    # Simple linear regression
    x_mean = statistics.mean(x)
    y_mean = statistics.mean(daily_values)

    numerator = sum((x[i] - x_mean) * (daily_values[i] - y_mean) for i in range(n))
    denominator = sum((x[i] - x_mean) ** 2 for i in range(n))

    if denominator == 0:
        slope = 0
    else:
        slope = numerator / denominator

    # Calculate percentage change over the period
    start_estimate = y_mean - slope * x_mean
    end_estimate = y_mean + slope * (n - 1 - x_mean)

    if start_estimate == 0:
        percentage_change = 100.0 if end_estimate > 0 else 0.0
    else:
        percentage_change = ((end_estimate - start_estimate) / abs(start_estimate)) * 100

    # Determine direction
    if percentage_change >= 5.0:
        direction = TrendDirection.UP
    elif percentage_change <= -5.0:
        direction = TrendDirection.DOWN
    else:
        direction = TrendDirection.STABLE

    # Confidence based on R-squared
    ss_res = sum((daily_values[i] - (start_estimate + slope * x[i])) ** 2 for i in range(n))
    ss_tot = sum((daily_values[i] - y_mean) ** 2 for i in range(n))
    r_squared = 1 - (ss_res / ss_tot) if ss_tot != 0 else 0

    if r_squared > 0.7:
        confidence = "high"
    elif r_squared > 0.4:
        confidence = "medium"
    else:
        confidence = "low"

    # Split for recent/prior averages
    mid = n // 2
    recent_avg = statistics.mean(daily_values[mid:])
    prior_avg = statistics.mean(daily_values[:mid])

    description = _generate_description(direction, percentage_change, recent_avg, prior_avg)

    return TrendResult(
        metric_name=metric_name,
        tenant_id=tenant_id,
        direction=direction,
        percentage_change=percentage_change,
        recent_average=recent_avg,
        prior_average=prior_avg,
        confidence=confidence,
        recent_period_days=n - mid,
        prior_period_days=mid,
        description=description,
    )
