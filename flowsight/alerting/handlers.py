"""
Alert Handlers

Built-in handlers for alert notifications: log, webhook, email.
"""

import smtplib
import json
from dataclasses import dataclass
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Any

import httpx

from flowsight import get_logger
from flowsight.alerting.manager import AlertHandler
from flowsight.alerting.threshold import Alert, AlertSeverity

logger = get_logger(__name__)


class LogHandler(AlertHandler):
    """Log alerts to structured logger."""

    def __init__(self, severity_filter: list[AlertSeverity] | None = None):
        super().__init__("log", severity_filter)

    async def handle(self, alert: Alert):
        """Log the alert."""
        log_data = {
            "rule": alert.rule_name,
            "severity": alert.severity.value,
            "message": alert.message,
            "timestamp": alert.timestamp.isoformat(),
            "flow_src_ip": alert.flow_data.get("src_ip"),
            "flow_dst_ip": alert.flow_data.get("dst_ip"),
            "flow_bytes": alert.flow_data.get("bytes"),
            "flow_packets": alert.flow_data.get("packets"),
        }

        if alert.severity == AlertSeverity.CRITICAL:
            logger.error("ALERT_CRITICAL", **log_data)
        elif alert.severity == AlertSeverity.WARNING:
            logger.warning("ALERT_WARNING", **log_data)
        else:
            logger.info("ALERT_INFO", **log_data)


class WebhookHandler(AlertHandler):
    """Send alerts to a webhook URL."""
    url: str
    headers: dict[str, str] | None = None
    template: str | None = None
    timeout: int = 10
    severity_filter: list[AlertSeverity] | None = None

    def __init__(
        self,
        url: str,
        headers: dict[str, str] | None = None,
        template: str | None = None,
        severity_filter: list[AlertSeverity] | None = None,
        timeout: int = 10,
    ):
        # Set fields before calling super().__init__
        self.url = url
        self.headers = headers or {"Content-Type": "application/json"}
        self.template = template
        self.timeout = timeout
        self.severity_filter = severity_filter
        super().__init__("webhook", severity_filter)

    async def handle(self, alert: Alert):
        """Send alert to webhook."""
        payload = self._format_payload(alert)

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(self.url, json=payload, headers=self.headers)
                response.raise_for_status()
                logger.debug("webhook_alert_sent", url=self.url, rule=alert.rule_name, status=response.status_code)
        except httpx.HTTPStatusError as e:
            logger.warning("webhook_alert_failed", url=self.url, status=e.response.status_code, error=str(e))
        except Exception as e:
            logger.exception("webhook_alert_error", url=self.url, error=str(e))

    def _format_payload(self, alert: Alert) -> dict[str, Any]:
        """Format alert payload for webhook."""
        if self.template:
            # Use custom template
            try:
                return json.loads(self.template.format(
                    rule=alert.rule_name,
                    severity=alert.severity.value,
                    message=alert.message,
                    timestamp=alert.timestamp.isoformat(),
                    src_ip=alert.flow_data.get("src_ip", ""),
                    dst_ip=alert.flow_data.get("dst_ip", ""),
                    bytes=alert.flow_data.get("bytes", 0),
                    packets=alert.flow_data.get("packets", 0),
                ))
            except Exception:
                pass

        # Default payload
        return {
            "alert": {
                "rule": alert.rule_name,
                "severity": alert.severity.value,
                "message": alert.message,
                "timestamp": alert.timestamp.isoformat(),
                "acknowledged": alert.acknowledged,
            },
            "flow": {
                "src_ip": alert.flow_data.get("src_ip"),
                "dst_ip": alert.flow_data.get("dst_ip"),
                "src_port": alert.flow_data.get("src_port"),
                "dst_port": alert.flow_data.get("dst_port"),
                "protocol": alert.flow_data.get("protocol"),
                "bytes": alert.flow_data.get("bytes"),
                "packets": alert.flow_data.get("packets"),
                "start_time": alert.flow_data.get("start_time"),
                "end_time": alert.flow_data.get("end_time"),
            },
        }


class EmailHandler(AlertHandler):
    """Send alerts via email (SMTP)."""
    smtp_host: str
    smtp_port: int
    username: str
    password: str
    from_email: str
    to_emails: list[str]
    use_tls: bool = True
    severity_filter: list[AlertSeverity] | None = None

    def __init__(
        self,
        smtp_host: str,
        smtp_port: int,
        username: str,
        password: str,
        from_email: str,
        to_emails: list[str],
        use_tls: bool = True,
        severity_filter: list[AlertSeverity] | None = None,
    ):
        # Set fields before calling super().__init__
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.username = username
        self.password = password
        self.from_email = from_email
        self.to_emails = to_emails
        self.use_tls = use_tls
        self.severity_filter = severity_filter
        super().__init__("email", severity_filter)

    async def handle(self, alert: Alert):
        """Send alert via email."""
        subject = f"[FlowSight Alert] {alert.severity.value.upper()}: {alert.rule_name}"
        body = self._format_email_body(alert)

        msg = MIMEMultipart()
        msg["From"] = self.from_email
        msg["To"] = ", ".join(self.to_emails)
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "html"))

        try:
            # Run SMTP in thread pool since smtplib is synchronous
            import asyncio
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self._send_email, msg)
            logger.info("email_alert_sent", rule=alert.rule_name, to=self.to_emails)
        except Exception as e:
            logger.exception("email_alert_failed", error=str(e))

    def _send_email(self, msg: MIMEMultipart):
        """Send email synchronously (runs in thread pool)."""
        with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
            if self.use_tls:
                server.starttls()
            server.login(self.username, self.password)
            server.send_message(msg)

    def _format_email_body(self, alert: Alert) -> str:
        """Format alert as HTML email."""
        severity_colors = {
            "critical": "#dc3545",
            "warning": "#ffc107",
            "info": "#17a2b8",
        }
        color = severity_colors.get(alert.severity.value, "#6c757d")

        return f"""
        <html>
        <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
            <div style="background-color: {color}; color: white; padding: 20px; border-radius: 5px 5px 0 0;">
                <h2 style="margin: 0;">FlowSight Alert: {alert.rule_name}</h2>
                <p style="margin: 10px 0 0;">Severity: {alert.severity.value.upper()}</p>
            </div>
            <div style="padding: 20px; border: 1px solid #ddd; border-top: none; border-radius: 0 0 5px 5px;">
                <p><strong>Message:</strong> {alert.message}</p>
                <p><strong>Timestamp:</strong> {alert.timestamp.isoformat()} UTC</p>
                <hr>
                <h3>Flow Details</h3>
                <table style="width: 100%; border-collapse: collapse;">
                    <tr><td style="padding: 8px; border-bottom: 1px solid #eee;"><strong>Source IP</strong></td><td style="padding: 8px; border-bottom: 1px solid #eee;">{alert.flow_data.get('src_ip', 'N/A')}</td></tr>
                    <tr><td style="padding: 8px; border-bottom: 1px solid #eee;"><strong>Destination IP</strong></td><td style="padding: 8px; border-bottom: 1px solid #eee;">{alert.flow_data.get('dst_ip', 'N/A')}</td></tr>
                    <tr><td style="padding: 8px; border-bottom: 1px solid #eee;"><strong>Source Port</strong></td><td style="padding: 8px; border-bottom: 1px solid #eee;">{alert.flow_data.get('src_port', 'N/A')}</td></tr>
                    <tr><td style="padding: 8px; border-bottom: 1px solid #eee;"><strong>Destination Port</strong></td><td style="padding: 8px; border-bottom: 1px solid #eee;">{alert.flow_data.get('dst_port', 'N/A')}</td></tr>
                    <tr><td style="padding: 8px; border-bottom: 1px solid #eee;"><strong>Protocol</strong></td><td style="padding: 8px; border-bottom: 1px solid #eee;">{alert.flow_data.get('protocol', 'N/A')}</td></tr>
                    <tr><td style="padding: 8px; border-bottom: 1px solid #eee;"><strong>Bytes</strong></td><td style="padding: 8px; border-bottom: 1px solid #eee;">{alert.flow_data.get('bytes', 'N/A'):,}</td></tr>
                    <tr><td style="padding: 8px; border-bottom: 1px solid #eee;"><strong>Packets</strong></td><td style="padding: 8px; border-bottom: 1px solid #eee;">{alert.flow_data.get('packets', 'N/A'):,}</td></tr>
                </table>
            </div>
            <div style="padding: 20px; text-align: center; color: #666; font-size: 12px;">
                <p>This alert was generated by FlowSight Network Flow Analyzer</p>
            </div>
        </body>
        </html>
        """