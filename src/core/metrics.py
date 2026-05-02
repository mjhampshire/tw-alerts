"""Metric definitions for alerting.

Each metric has:
- name: Unique identifier
- display_name: Human-readable name for alerts
- query_template: ClickHouse query to fetch the metric value
- min_volume: Minimum absolute value to consider (avoid low-volume noise)
- drop_threshold: Z-score threshold for drop alerts (negative)
- spike_threshold: Z-score threshold for spike alerts (positive)
- min_history_weeks: Minimum weeks of history required
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class MetricDefinition:
    """Definition of a metric to monitor."""
    name: str
    display_name: str
    description: str
    query_template: str  # ClickHouse query with {tenant_id}, {date} placeholders
    min_volume: int = 5  # Minimum absolute value to alert on
    drop_threshold: float = -2.5  # Z-score for drops (more sensitive)
    spike_threshold: float = 3.5  # Z-score for spikes (less sensitive)
    min_history_weeks: int = 4  # Minimum weeks of baseline data
    unit: str = "count"  # "count", "currency", "percentage"


# Initial metrics to monitor
METRICS = {
    "wishlist_items_notify_me": MetricDefinition(
        name="wishlist_items_notify_me",
        display_name="Wishlist Items (Notify Me)",
        description="Items added to wishlist with customerInterest=1 and notifyMe=1",
        query_template="""
            SELECT count(*) as value
            FROM TWCWISHLIST_ITEM
            WHERE tenantId = '{tenant_id}'
              AND toDate(createdAt) = '{date}'
              AND customerInterest = 1
              AND notifyMe = 1
        """,
        min_volume=3,
    ),

    "wishlist_items_standard": MetricDefinition(
        name="wishlist_items_standard",
        display_name="Wishlist Items Added",
        description="Items added to wishlist with customerInterest=0 (standard adds)",
        query_template="""
            SELECT count(*) as value
            FROM TWCWISHLIST_ITEM
            WHERE tenantId = '{tenant_id}'
              AND toDate(createdAt) = '{date}'
              AND customerInterest = 0
        """,
        min_volume=5,
    ),

    "price_drop_notifications": MetricDefinition(
        name="price_drop_notifications",
        display_name="Price Drop Notifications",
        description="Price drop notifications sent to customers",
        query_template="""
            SELECT count(*) as value
            FROM TWCNOTIFICATION
            WHERE tenantId = '{tenant_id}'
              AND toDate(createdAt) = '{date}'
              AND notificationType = 'price_drop'
        """,
        min_volume=3,
    ),

    "revenue_generated": MetricDefinition(
        name="revenue_generated",
        display_name="Revenue Generated",
        description="Total revenue from wishlist-attributed orders",
        query_template="""
            SELECT coalesce(sum(orderTotal), 0) as value
            FROM TWCORDER
            WHERE tenantId = '{tenant_id}'
              AND toDate(createdAt) = '{date}'
              AND wishlistAttributed = 1
        """,
        min_volume=100,  # $100 minimum
        unit="currency",
    ),

    "wishlists_created": MetricDefinition(
        name="wishlists_created",
        display_name="Wishlists Created",
        description="New wishlists created",
        query_template="""
            SELECT count(*) as value
            FROM TWCWISHLIST
            WHERE tenantId = '{tenant_id}'
              AND toDate(createdAt) = '{date}'
        """,
        min_volume=3,
    ),
}


def get_metric(name: str) -> Optional[MetricDefinition]:
    """Get a metric definition by name."""
    return METRICS.get(name)


def get_all_metrics() -> list[MetricDefinition]:
    """Get all metric definitions."""
    return list(METRICS.values())
