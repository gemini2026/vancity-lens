"""
VanCity Lens -- Email delivery service for weekly undervalued parcel alerts (F06-002).

Uses smtplib in a thread executor to avoid blocking the async event loop.
All SMTP configuration is lazy-loaded from environment variables to prevent
import-time failures in tests or when SMTP is not configured.

Environment variables (all optional -- gracefully degrades if missing):
    SMTP_HOST       SMTP server hostname (e.g. smtp.gmail.com)
    SMTP_PORT       SMTP server port (default 587)
    SMTP_USER       SMTP authentication username
    SMTP_PASSWORD   SMTP authentication password
    EMAIL_FROM      Sender address (default: noreply@vancitylens.com)
"""

import asyncio
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

logger = logging.getLogger(__name__)


def _get_smtp_config() -> Optional[dict]:
    """
    Lazy-load SMTP configuration from environment variables.

    Returns None if required variables (SMTP_HOST) are not set,
    allowing callers to gracefully skip email delivery.
    """
    import os

    host = os.environ.get("SMTP_HOST")
    if not host:
        return None

    return {
        "host": host,
        "port": int(os.environ.get("SMTP_PORT", "587")),
        "user": os.environ.get("SMTP_USER", ""),
        "password": os.environ.get("SMTP_PASSWORD", ""),
        "from_addr": os.environ.get("EMAIL_FROM", "noreply@vancitylens.com"),
    }


def _send_email_sync(to: str, subject: str, html_body: str) -> bool:
    """
    Synchronous email send via smtplib.

    Returns True on success, False on failure.
    This function is designed to be called inside a thread executor.
    """
    config = _get_smtp_config()
    if config is None:
        logger.warning(
            "SMTP not configured (SMTP_HOST not set). "
            "Skipping email to %s.",
            to,
        )
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = config["from_addr"]
    msg["To"] = to
    msg.attach(MIMEText(html_body, "html"))

    try:
        with smtplib.SMTP(config["host"], config["port"], timeout=30) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            if config["user"] and config["password"]:
                server.login(config["user"], config["password"])
            server.sendmail(config["from_addr"], [to], msg.as_string())
        logger.info("Email sent successfully to %s: %s", to, subject)
        return True
    except Exception as e:
        logger.error(
            "Failed to send email to %s: %s (%s)",
            to,
            e,
            type(e).__name__,
            exc_info=True,
        )
        return False


async def send_email(to: str, subject: str, html_body: str) -> bool:
    """
    Async wrapper that sends email in a thread executor.

    Args:
        to: Recipient email address.
        subject: Email subject line.
        html_body: HTML content of the email body.

    Returns:
        True if the email was sent successfully, False otherwise.
    """
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _send_email_sync, to, subject, html_body)


def _format_currency(value: int) -> str:
    """Format an integer as a currency string (e.g. $1,234,567)."""
    if value is None:
        return "N/A"
    return f"${value:,.0f}"


def _build_undervalued_html(parcels: list[dict]) -> str:
    """
    Build an HTML email body for the weekly undervalued parcel digest.

    Args:
        parcels: List of parcel dicts, each containing at minimum:
            pid, neighborhood, assessed_value, implied_value,
            discount_pct, civic_address, current_zoning
    """
    rows_html = ""
    for i, p in enumerate(parcels, 1):
        pid = p.get("pid", "?")
        neighborhood = p.get("neighborhood", "N/A")
        address = p.get("civic_address", "N/A") or "N/A"
        zoning = p.get("current_zoning", "N/A") or "N/A"
        assessed = _format_currency(p.get("assessed_value"))
        implied = _format_currency(p.get("implied_value"))
        discount = p.get("discount_pct")
        discount_str = f"{float(discount):.1f}%" if discount is not None else "N/A"
        tod_tier = p.get("tod_tier", "N/A") or "N/A"

        bg = "#f8fafc" if i % 2 == 0 else "#ffffff"
        rows_html += f"""
        <tr style="background-color: {bg};">
            <td style="padding: 8px 12px; border-bottom: 1px solid #e2e8f0; text-align: center; font-weight: 600;">{i}</td>
            <td style="padding: 8px 12px; border-bottom: 1px solid #e2e8f0;">
                <strong>{pid}</strong><br>
                <span style="color: #64748b; font-size: 13px;">{address}</span>
            </td>
            <td style="padding: 8px 12px; border-bottom: 1px solid #e2e8f0;">{neighborhood}</td>
            <td style="padding: 8px 12px; border-bottom: 1px solid #e2e8f0;">{zoning}</td>
            <td style="padding: 8px 12px; border-bottom: 1px solid #e2e8f0; text-align: right;">{assessed}</td>
            <td style="padding: 8px 12px; border-bottom: 1px solid #e2e8f0; text-align: right;">{implied}</td>
            <td style="padding: 8px 12px; border-bottom: 1px solid #e2e8f0; text-align: center; color: #16a34a; font-weight: 700;">{discount_str}</td>
            <td style="padding: 8px 12px; border-bottom: 1px solid #e2e8f0; text-align: center;">{tod_tier}</td>
        </tr>"""

    from datetime import date

    today = date.today().strftime("%B %d, %Y")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>VanCity Lens - Weekly Undervalued Parcel Alert</title>
</head>
<body style="margin: 0; padding: 0; background-color: #f1f5f9; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;">
    <div style="max-width: 900px; margin: 0 auto; padding: 24px;">
        <!-- Header -->
        <div style="background: linear-gradient(135deg, #1e3a5f 0%, #0f172a 100%); color: #ffffff; padding: 24px 32px; border-radius: 8px 8px 0 0;">
            <h1 style="margin: 0 0 4px 0; font-size: 22px; font-weight: 700;">VanCity Lens</h1>
            <p style="margin: 0; font-size: 14px; color: #93c5fd;">Weekly Undervalued Parcel Alert &mdash; {today}</p>
        </div>

        <!-- Intro -->
        <div style="background: #ffffff; padding: 24px 32px; border-left: 1px solid #e2e8f0; border-right: 1px solid #e2e8f0;">
            <p style="margin: 0 0 8px 0; font-size: 15px; color: #334155;">
                Here are the <strong>top {len(parcels)} undervalued parcels</strong> ranked by
                discount percentage (assessed value vs. implied development value).
            </p>
            <p style="margin: 0; font-size: 13px; color: #94a3b8;">
                Parcels with active development applications have been excluded.
            </p>
        </div>

        <!-- Table -->
        <div style="background: #ffffff; padding: 0 32px 24px 32px; border-left: 1px solid #e2e8f0; border-right: 1px solid #e2e8f0; overflow-x: auto;">
            <table style="width: 100%; border-collapse: collapse; font-size: 14px; color: #1e293b;">
                <thead>
                    <tr style="background-color: #f1f5f9;">
                        <th style="padding: 10px 12px; text-align: center; font-weight: 600; border-bottom: 2px solid #cbd5e1;">#</th>
                        <th style="padding: 10px 12px; text-align: left; font-weight: 600; border-bottom: 2px solid #cbd5e1;">PID / Address</th>
                        <th style="padding: 10px 12px; text-align: left; font-weight: 600; border-bottom: 2px solid #cbd5e1;">Neighborhood</th>
                        <th style="padding: 10px 12px; text-align: left; font-weight: 600; border-bottom: 2px solid #cbd5e1;">Zoning</th>
                        <th style="padding: 10px 12px; text-align: right; font-weight: 600; border-bottom: 2px solid #cbd5e1;">Assessed</th>
                        <th style="padding: 10px 12px; text-align: right; font-weight: 600; border-bottom: 2px solid #cbd5e1;">Implied</th>
                        <th style="padding: 10px 12px; text-align: center; font-weight: 600; border-bottom: 2px solid #cbd5e1;">Discount</th>
                        <th style="padding: 10px 12px; text-align: center; font-weight: 600; border-bottom: 2px solid #cbd5e1;">TOD Tier</th>
                    </tr>
                </thead>
                <tbody>
                    {rows_html}
                </tbody>
            </table>
        </div>

        <!-- Footer -->
        <div style="background: #f8fafc; padding: 16px 32px; border: 1px solid #e2e8f0; border-radius: 0 0 8px 8px; text-align: center;">
            <p style="margin: 0 0 8px 0; font-size: 12px; color: #94a3b8;">
                This is an automated alert from VanCity Lens. Scores are based on
                BC Assessment data and comparable transaction analysis. This is not
                financial advice &mdash; always perform independent due diligence.
            </p>
            <p style="margin: 0; font-size: 12px; color: #94a3b8;">
                To unsubscribe, update your email preferences in your VanCity Lens account settings.
            </p>
        </div>
    </div>
</body>
</html>"""


async def send_undervalued_alert(to: str, parcels: list[dict]) -> bool:
    """
    Send the weekly undervalued parcel digest email.

    Args:
        to: Recipient email address.
        parcels: List of top-20 undervalued parcel dicts.

    Returns:
        True if the email was sent successfully, False otherwise.
    """
    if not parcels:
        logger.warning("No parcels to send in undervalued alert to %s", to)
        return False

    html_body = _build_undervalued_html(parcels)
    subject = f"VanCity Lens: Weekly Undervalued Parcel Alert ({len(parcels)} opportunities)"
    return await send_email(to, subject, html_body)
