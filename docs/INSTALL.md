# Installation Guide

## Prerequisites

- Python 3.10+
- ClickHouse database
- Access to TWC metric tables in ClickHouse

## Installation

### 1. Clone the Repository

```bash
git clone git@github.com:mjhampshire/tw-alerts.git
cd tw-alerts
```

### 2. Create Virtual Environment

```bash
python -m venv venv
source venv/bin/activate  # Linux/macOS
# or
venv\Scripts\activate     # Windows
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure Environment

```bash
cp .env.example .env
```

Edit `.env` with your settings:

```env
# ClickHouse connection
CLICKHOUSE_HOST=your-clickhouse-host
CLICKHOUSE_PORT=8123
CLICKHOUSE_USER=default
CLICKHOUSE_PASSWORD=your-password
CLICKHOUSE_DATABASE=default

# Notification webhooks (optional)
ALERT_WEBHOOK_DEFAULT=https://your-webhook-url
ALERT_SLACK_DEFAULT=https://hooks.slack.com/services/xxx
```

### 5. Run Database Migration

Connect to ClickHouse and run the migration:

```bash
clickhouse-client --host your-host --query "$(cat migrations/001_create_alerts_table.sql)"
```

Or via the ClickHouse HTTP interface:

```bash
curl -X POST "http://your-host:8123/" \
  --data-binary @migrations/001_create_alerts_table.sql
```

### 6. Verify Installation

Start the API server:

```bash
python -m src.api.app
```

Check health endpoint:

```bash
curl http://localhost:8000/health
# {"status": "healthy"}
```

## Production Deployment

### Running the API Server

Using uvicorn directly:

```bash
uvicorn src.api.app:app --host 0.0.0.0 --port 8000 --workers 4
```

Using gunicorn with uvicorn workers:

```bash
pip install gunicorn
gunicorn src.api.app:app -w 4 -k uvicorn.workers.UvicornWorker -b 0.0.0.0:8000
```

### Setting Up the CRON Job

Add to crontab to run daily at 6 AM:

```bash
crontab -e
```

Add the following line:

```
0 6 * * * /path/to/venv/bin/python -m src.jobs.detect_anomalies >> /var/log/twc-alerts.log 2>&1
```

### Docker Deployment

Create a `Dockerfile`:

```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ src/
COPY migrations/ migrations/

CMD ["uvicorn", "src.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
```

Build and run:

```bash
docker build -t twc-alerts .
docker run -p 8000:8000 --env-file .env twc-alerts
```

### Kubernetes CronJob

For the detection job:

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: twc-alerts-detector
spec:
  schedule: "0 6 * * *"
  jobTemplate:
    spec:
      template:
        spec:
          containers:
          - name: detector
            image: twc-alerts:latest
            command: ["python", "-m", "src.jobs.detect_anomalies"]
            envFrom:
            - secretRef:
                name: twc-alerts-secrets
          restartPolicy: OnFailure
```

## Configuration Options

### Per-Tenant Webhooks

Set tenant-specific notification URLs using environment variables:

```env
# Format: ALERT_WEBHOOK_{TENANT_ID_UPPERCASE}
ALERT_WEBHOOK_VIKTORIA_WOODS=https://webhook.site/tenant-specific
ALERT_SLACK_VIKTORIA_WOODS=https://hooks.slack.com/services/tenant-specific
```

Falls back to `ALERT_WEBHOOK_DEFAULT` if tenant-specific URL not set.

## Troubleshooting

### Connection Refused to ClickHouse

Verify ClickHouse is running and accessible:

```bash
curl http://your-host:8123/ping
# Ok.
```

### No Alerts Generated

1. Check that metric tables exist and have data
2. Verify tenant IDs match between metric tables and alert queries
3. Run a manual check:

```bash
curl -X POST http://localhost:8000/api/v1/alerts/your-tenant/check \
  -H "Content-Type: application/json" \
  -d '{"metric_name": "wishlist_items_notify_me"}'
```

### Alerts Not Sending

Check logs for notification errors. Common issues:

- Invalid webhook URL
- Slack webhook expired
- Network connectivity
