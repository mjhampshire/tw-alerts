"""Alert notification services - email, webhook, in-app."""

from abc import ABC, abstractmethod
from typing import Optional
import logging
import json

import httpx

from .models import Alert

logger = logging.getLogger(__name__)


class Notifier(ABC):
    """Base class for alert notifiers."""

    @abstractmethod
    async def send(self, alert: Alert, recipient: str) -> bool:
        """Send an alert notification."""
        pass


class WebhookNotifier(Notifier):
    """Send alerts via webhook."""

    def __init__(self, timeout: float = 10.0):
        self.timeout = timeout

    async def send(self, alert: Alert, webhook_url: str) -> bool:
        """
        Send alert to a webhook URL.

        The webhook receives a JSON payload with the full alert details.
        """
        payload = {
            "event": "alert.created",
            "alert": alert.to_dict(),
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    webhook_url,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                )
                response.raise_for_status()
                logger.info(f"Sent webhook alert {alert.id} to {webhook_url}")
                return True
        except Exception as e:
            logger.error(f"Failed to send webhook alert {alert.id}: {e}")
            return False


class EmailNotifier(Notifier):
    """Send alerts via email using an email service."""

    def __init__(
        self,
        api_url: str,
        api_key: str,
        from_email: str = "alerts@thewishlist.io",
        from_name: str = "TWC Alerts",
    ):
        self.api_url = api_url
        self.api_key = api_key
        self.from_email = from_email
        self.from_name = from_name

    async def send(self, alert: Alert, to_email: str) -> bool:
        """
        Send alert via email.

        Formats the alert as a readable email with key metrics.
        """
        subject = self._build_subject(alert)
        html_body = self._build_html_body(alert)

        payload = {
            "from": {"email": self.from_email, "name": self.from_name},
            "to": [{"email": to_email}],
            "subject": subject,
            "html": html_body,
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.api_url,
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                )
                response.raise_for_status()
                logger.info(f"Sent email alert {alert.id} to {to_email}")
                return True
        except Exception as e:
            logger.error(f"Failed to send email alert {alert.id}: {e}")
            return False

    def _build_subject(self, alert: Alert) -> str:
        """Build email subject line."""
        emoji = "📉" if alert.alert_type == "drop" else "📈"
        severity_emoji = {
            "critical": "🔴",
            "high": "🟠",
            "medium": "🟡",
            "low": "🟢",
        }.get(alert.severity.value, "")

        return (
            f"{severity_emoji} {emoji} {alert.metric_display_name} "
            f"{'dropped' if alert.alert_type == 'drop' else 'spiked'} "
            f"by {abs(alert.percentage_change):.0f}%"
        )

    def _build_html_body(self, alert: Alert) -> str:
        """Build HTML email body."""
        direction = "dropped" if alert.alert_type == "drop" else "spiked"
        color = "#dc3545" if alert.alert_type == "drop" else "#28a745"

        if alert.unit == "currency":
            current_str = f"${alert.current_value:,.2f}"
            baseline_str = f"${alert.baseline_value:,.2f}"
        else:
            current_str = f"{alert.current_value:,.0f}"
            baseline_str = f"{alert.baseline_value:,.0f}"

        return f"""
        <html>
        <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
            <div style="background: #f8f9fa; padding: 20px; border-radius: 8px;">
                <h2 style="color: {color}; margin-top: 0;">
                    {alert.metric_display_name} {direction}
                </h2>

                <p style="font-size: 16px; color: #333;">
                    {alert.message}
                </p>

                <table style="width: 100%; border-collapse: collapse; margin: 20px 0;">
                    <tr>
                        <td style="padding: 10px; border: 1px solid #dee2e6;">
                            <strong>Current Value</strong><br>
                            <span style="font-size: 24px; color: {color};">{current_str}</span>
                        </td>
                        <td style="padding: 10px; border: 1px solid #dee2e6;">
                            <strong>Normal (Baseline)</strong><br>
                            <span style="font-size: 24px;">{baseline_str}</span>
                        </td>
                    </tr>
                    <tr>
                        <td style="padding: 10px; border: 1px solid #dee2e6;">
                            <strong>Change</strong><br>
                            <span style="font-size: 18px; color: {color};">
                                {'+' if alert.percentage_change > 0 else ''}{alert.percentage_change:.1f}%
                            </span>
                        </td>
                        <td style="padding: 10px; border: 1px solid #dee2e6;">
                            <strong>Severity</strong><br>
                            <span style="font-size: 18px;">{alert.severity.value.upper()}</span>
                        </td>
                    </tr>
                </table>

                <p style="color: #666; font-size: 14px;">
                    Date: {alert.date}<br>
                    Alert ID: {alert.id}
                </p>

                <hr style="border: none; border-top: 1px solid #dee2e6; margin: 20px 0;">

                <p style="color: #999; font-size: 12px;">
                    This alert was generated automatically by TWC Analytics.
                    <a href="#">View in dashboard</a> | <a href="#">Dismiss alert</a>
                </p>
            </div>
        </body>
        </html>
        """


class SlackNotifier(Notifier):
    """Send alerts to Slack via webhook."""

    async def send(self, alert: Alert, webhook_url: str) -> bool:
        """Send alert as Slack message."""
        emoji = ":chart_with_downwards_trend:" if alert.alert_type == "drop" else ":chart_with_upwards_trend:"
        color = "#dc3545" if alert.alert_type == "drop" else "#28a745"

        payload = {
            "attachments": [
                {
                    "color": color,
                    "blocks": [
                        {
                            "type": "header",
                            "text": {
                                "type": "plain_text",
                                "text": f"{emoji} {alert.metric_display_name}",
                            },
                        },
                        {
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": alert.message,
                            },
                        },
                        {
                            "type": "section",
                            "fields": [
                                {"type": "mrkdwn", "text": f"*Current:*\n{alert.current_value:,.0f}"},
                                {"type": "mrkdwn", "text": f"*Normal:*\n{alert.baseline_value:,.0f}"},
                                {"type": "mrkdwn", "text": f"*Change:*\n{alert.percentage_change:+.1f}%"},
                                {"type": "mrkdwn", "text": f"*Severity:*\n{alert.severity.value.upper()}"},
                            ],
                        },
                        {
                            "type": "context",
                            "elements": [
                                {"type": "mrkdwn", "text": f"Date: {alert.date} | ID: {alert.id}"},
                            ],
                        },
                    ],
                }
            ]
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(webhook_url, json=payload)
                response.raise_for_status()
                logger.info(f"Sent Slack alert {alert.id}")
                return True
        except Exception as e:
            logger.error(f"Failed to send Slack alert {alert.id}: {e}")
            return False
