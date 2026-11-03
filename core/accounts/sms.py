"""Sending one SMS through the Teleconic REST API (https://sms.teleconic.com/api/v1).

Server-side only: the API key comes from settings (SMS_API_KEY) and never reaches a client.
Uses the standard library (no extra packages). A send is queued by Teleconic; success means
accepted, not delivered. Each send carries an Idempotency-Key, so a retry never double-charges.
"""

import json
import logging
import secrets
import urllib.error
import urllib.request

from django.conf import settings

logger = logging.getLogger("accounts.sms")


def send_sms(to: str, message: str, reference: str = "") -> bool:
    """Queue `message` to `to` (digits with country code). True when Teleconic accepted it.

    Without an API key nothing is sent: in DEBUG the message is logged (for local testing),
    otherwise the send fails.
    """
    if not settings.SMS_API_KEY:
        if settings.DEBUG:
            logger.warning("SMS_API_KEY is not set; not sent to %s: %s", to, message)
            return True
        logger.error("SMS_API_KEY is not set; cannot send SMS")
        return False
    payload: dict[str, str] = {"to": to, "message": message}
    if settings.SMS_SENDER_ID:
        payload["sender_id"] = settings.SMS_SENDER_ID
    if reference:
        payload["reference"] = reference[:100]
    request = urllib.request.Request(
        f"{settings.SMS_API_URL.rstrip('/')}/sms/send",
        data=json.dumps(payload).encode(),
        method="POST",
        headers={
            "Authorization": f"Bearer {settings.SMS_API_KEY}",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Idempotency-Key": secrets.token_hex(16),
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=settings.SMS_TIMEOUT_SECONDS) as response:
            body = json.loads(response.read() or b"{}")
    except urllib.error.HTTPError as exc:
        logger.error("SMS send failed: HTTP %s (%s)", exc.code, _error_text(exc))
        return False
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        logger.error("SMS send failed: %s", exc)
        return False
    if not body.get("success"):
        logger.error("SMS send rejected: %s", body.get("error"))
        return False
    return True


def _error_text(exc: urllib.error.HTTPError) -> str:
    try:
        return str(json.loads(exc.read() or b"{}").get("error", ""))
    except ValueError:
        return ""
