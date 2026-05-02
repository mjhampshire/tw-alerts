-- TWC Alerts table for storing anomaly alerts
-- Run this migration against your ClickHouse database

CREATE TABLE IF NOT EXISTS default.TWCALERT (
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
ORDER BY (tenantId, alertDate, metricName, id);
