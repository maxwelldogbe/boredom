"""Pseudonymous guest keys. The raw browser profile id is never stored."""

import hashlib
import hmac

from django.conf import settings

from games.constants import GUEST_KEY_LENGTH


def guest_key(profile_id: str) -> str:
    """First GUEST_KEY_LENGTH hex chars of HMAC-SHA256(SECRET_KEY, profile id)."""
    digest = hmac.new(settings.SECRET_KEY.encode(), profile_id.encode(), hashlib.sha256)
    return digest.hexdigest()[:GUEST_KEY_LENGTH]
