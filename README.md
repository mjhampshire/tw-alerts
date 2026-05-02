# TWC Alerts

Anomaly detection and alerting system for TWC metrics. Automatically detects unusual drops or spikes in key business metrics and sends notifications.

## Features

- **Robust anomaly detection** using Median + MAD (Median Absolute Deviation)
- **Day-of-week aware** baselines (compares Monday to past Mondays)
- **Asymmetric thresholds** for drops vs spikes
- **Multi-channel notifications** via webhook, email, and Slack
- **Alert management API** with status tracking
- **Deduplication** to prevent alert fatigue

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your ClickHouse credentials

# Run the API server
python -m src.api.app

# Run anomaly detection (typically via cron)
python -m src.jobs.detect_anomalies
```

## Monitored Metrics

| Metric | Description | Drop Threshold | Spike Threshold |
|--------|-------------|----------------|-----------------|
| Wishlist Items (Notify Me) | Back-in-stock notification signups | -2.5σ | +3.5σ |
| Wishlist Items (Standard) | Regular wishlist additions | -2.5σ | +3.5σ |
| Price Drop Notifications | Price alert signups | -2.5σ | +3.5σ |
| Revenue Generated | Revenue from TWC features | -2.0σ | +4.0σ |
| Wishlists Created | New wishlist creations | -2.5σ | +3.5σ |

## API Endpoints

### Alerts

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/alerts/{tenant_id}` | List alerts for tenant |
| GET | `/api/v1/alerts/{tenant_id}/active` | Get active alerts |
| GET | `/api/v1/alerts/{tenant_id}/{alert_id}` | Get single alert |
| PUT | `/api/v1/alerts/{tenant_id}/{alert_id}` | Update alert status |
| POST | `/api/v1/alerts/{tenant_id}/check` | Manual metric check |
| GET | `/api/v1/alerts/metrics/list` | List available metrics |

### Trends

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/trends/{tenant_id}` | Get trends for all metrics |
| GET | `/api/v1/trends/{tenant_id}/{metric_name}` | Get trend for specific metric |

**Example trend response:**
```json
{
  "metric_name": "wishlist_items_notify_me",
  "metric_display_name": "Wishlist Items (Notify Me)",
  "direction": "up",
  "percentage_change": 15.3,
  "description": "Trending up +15.3% (142 → 164)",
  "confidence": "high"
}
```

## Documentation

- [Installation Guide](docs/INSTALL.md) - Deployment and setup
- [User Guide](docs/USER_GUIDE.md) - Using the alerts system
- [Developer Guide](docs/DEVELOPER_GUIDE.md) - Extending and customizing

## Architecture

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  CRON Job       │────▶│  Anomaly Engine  │────▶│  Alert Storage  │
│  (daily 6 AM)   │     │  Median + MAD    │     │  (ClickHouse)   │
└─────────────────┘     └──────────────────┘     └─────────────────┘
                                │
                                ▼
                        ┌──────────────────┐
                        │  Notifications   │
                        │  Webhook/Slack   │
                        └──────────────────┘
```

## License

Proprietary - The Wishlist Company
