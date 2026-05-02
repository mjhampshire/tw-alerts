# User Guide

## Overview

TWC Alerts provides two types of metric insights:

1. **Anomaly Alerts** - Notifications when unusual changes occur (something to look out for)
2. **Trend Analysis** - Advisory information showing if metrics are trending up, down, or stable

## How It Works

### What Gets Monitored

The system tracks these metrics daily:

| Metric | What It Measures |
|--------|------------------|
| **Wishlist Items (Notify Me)** | Customers signing up for back-in-stock notifications |
| **Wishlist Items (Standard)** | Regular wishlist additions |
| **Price Drop Notifications** | Customers signing up for price alerts |
| **Revenue Generated** | Revenue attributed to TWC features |
| **Wishlists Created** | New wishlists created |

### How Anomalies Are Detected

The system compares today's value against a baseline built from the **same day of week** over the past 8 weeks. This accounts for natural weekly patterns (e.g., weekends typically have different traffic than weekdays).

An alert is triggered when:
- **Drop**: Value falls significantly below normal (e.g., 50%+ drop)
- **Spike**: Value rises significantly above normal (e.g., 100%+ increase)

The system uses robust statistics (median + MAD) that aren't skewed by outliers like Black Friday.

### Alert Severity

| Severity | Meaning |
|----------|---------|
| **Critical** | Extreme deviation (>5σ) - immediate attention needed |
| **High** | Large deviation (3-5σ) - investigate soon |
| **Medium** | Moderate deviation (2.5-3σ) - review when possible |
| **Low** | Minor deviation - for awareness |

## Understanding Alerts

### Alert Message Format

```
Revenue Generated dropped by 65.2%. Current: $1,234.56, Normal: $3,550.00
```

This tells you:
- **Metric**: Revenue Generated
- **Direction**: dropped (could also be "spiked")
- **Change**: 65.2% below normal
- **Current value**: What was recorded today
- **Normal value**: The baseline median

### Slack Notifications

Slack alerts include:
- Metric name with trend emoji
- Alert message
- Current vs normal values
- Percentage change
- Severity level
- Date and alert ID

### Email Notifications

Email alerts provide a formatted summary with:
- Visual severity indicators
- Side-by-side value comparison
- Link to dashboard (if configured)
- Option to dismiss

## Managing Alerts

### Alert Statuses

| Status | Meaning |
|--------|---------|
| **Active** | New alert, needs attention |
| **Acknowledged** | Someone is looking into it |
| **Resolved** | Issue has been fixed |
| **Dismissed** | Expected behavior, no action needed |

### Acknowledging an Alert

When you start investigating an alert, acknowledge it so your team knows it's being handled:

```bash
curl -X PUT http://alerts-api/api/v1/alerts/{tenant_id}/{alert_id} \
  -H "Content-Type: application/json" \
  -d '{
    "status": "acknowledged",
    "acknowledged_by": "your-name",
    "notes": "Investigating the integration issue"
  }'
```

### Resolving an Alert

Once the issue is fixed:

```bash
curl -X PUT http://alerts-api/api/v1/alerts/{tenant_id}/{alert_id} \
  -H "Content-Type: application/json" \
  -d '{
    "status": "resolved",
    "notes": "Fixed API timeout issue"
  }'
```

### Dismissing Expected Alerts

If the change was expected (e.g., planned maintenance, known promotion):

```bash
curl -X PUT http://alerts-api/api/v1/alerts/{tenant_id}/{alert_id} \
  -H "Content-Type: application/json" \
  -d '{
    "status": "dismissed",
    "notes": "Expected: Black Friday sale caused spike"
  }'
```

## Viewing Alerts

### List All Alerts

```bash
curl http://alerts-api/api/v1/alerts/{tenant_id}
```

### Filter by Status

```bash
curl "http://alerts-api/api/v1/alerts/{tenant_id}?status=active"
```

### Get Active Alerts Only

```bash
curl http://alerts-api/api/v1/alerts/{tenant_id}/active
```

### View Single Alert

```bash
curl http://alerts-api/api/v1/alerts/{tenant_id}/{alert_id}
```

## Manual Metric Check

To check a metric on-demand (useful for debugging):

```bash
curl -X POST http://alerts-api/api/v1/alerts/{tenant_id}/check \
  -H "Content-Type: application/json" \
  -d '{"metric_name": "revenue_generated"}'
```

Response:
```json
{
  "metric_name": "revenue_generated",
  "tenant_id": "your-tenant",
  "date": "2024-01-15",
  "current_value": 1234.56,
  "baseline_median": 3550.00,
  "z_score": -3.2,
  "is_anomaly": true,
  "anomaly_type": "drop",
  "percentage_change": -65.2
}
```

## Common Scenarios

### "Why did I get an alert?"

Check the z-score and percentage change:
- **z-score**: How many standard deviations from normal (-3.2 = 3.2 below)
- **percentage_change**: Intuitive measure of the difference

### "Is this a false positive?"

Common causes of expected variations:
- Holidays or special events
- Marketing campaigns
- Site maintenance
- Seasonal patterns not yet captured

If it's expected, dismiss the alert with a note explaining why.

### "Why didn't I get an alert?"

The system has safeguards to prevent noise:
- **Deduplication**: Same alert won't fire multiple days in a row
- **Minimum volume**: Very low-traffic metrics may not trigger
- **Minimum history**: New metrics need 4+ weeks of baseline data

### "Can I test the alerts?"

Use the manual check endpoint to see what would be detected:

```bash
curl -X POST http://alerts-api/api/v1/alerts/{tenant_id}/check \
  -H "Content-Type: application/json" \
  -d '{"metric_name": "wishlist_items_notify_me", "target_date": "2024-01-15"}'
```

## Trend Analysis

Trends are different from alerts. While alerts notify you of unusual events, trends tell you the general direction of a metric over time.

### Getting Trends

**Single metric:**
```bash
curl http://alerts-api/api/v1/trends/{tenant_id}/wishlist_items_notify_me
```

**All metrics:**
```bash
curl http://alerts-api/api/v1/trends/{tenant_id}
```

### Understanding Trend Responses

```json
{
  "metric_name": "wishlist_items_notify_me",
  "metric_display_name": "Wishlist Items (Notify Me)",
  "direction": "up",
  "percentage_change": 15.3,
  "recent_average": 164,
  "prior_average": 142,
  "confidence": "high",
  "description": "Trending up +15.3% (142 → 164)"
}
```

| Field | Description |
|-------|-------------|
| **direction** | `up`, `down`, `stable`, or `insufficient_data` |
| **percentage_change** | Change between recent and prior period |
| **recent_average** | Average value over recent period (default 7 days) |
| **prior_average** | Average value over prior period (7 days before recent) |
| **confidence** | `high`, `medium`, or `low` based on data consistency |
| **description** | Human-readable summary for display |

### Trend Thresholds

- **Up**: 5%+ increase from prior to recent period
- **Down**: 5%+ decrease from prior to recent period
- **Stable**: Less than 5% change in either direction

### Custom Time Periods

Adjust the comparison periods:

```bash
# Compare last 14 days to previous 14 days
curl "http://alerts-api/api/v1/trends/{tenant_id}/revenue_generated?recent_days=14&prior_days=14"
```

### Using Trends in Your Frontend

Trends are designed to be displayed as advisory information:

- "Wishlist signups are **trending up** +15%"
- "Revenue is **stable** this week"
- "Notifications are **trending down** -8%"

The `description` field provides ready-to-use text for display.
