"""The bridge between accounts and the in-memory rooms: load a seat's saved profile from
an authToken, and add finished games to PlayerStats.
"""

import logging

from channels.db import database_sync_to_async
from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import F

from accounts.models import PlayerStats
from accounts.models import Profile as SavedProfile
from accounts.tokens import user_id_from_token
from rooms.models_types import Avatar, Profile

logger = logging.getLogger("accounts")


async def account_profile(token: object) -> Profile | None:
    """The saved profile of the active account a valid authToken names, else None.

    Database errors also give None (the player then joins as a guest) and are logged.
    """
    user_id = user_id_from_token(token)
    if user_id is None:
        return None
    try:
        return await _load_profile(user_id)
    except Exception:
        logger.exception("Could not load account profile: user=%s", user_id)
        return None


@database_sync_to_async
def _load_profile(user_id: int) -> Profile | None:
    saved = SavedProfile.objects.filter(user_id=user_id, user__is_active=True).first()
    if saved is None:
        return None
    return Profile(
        id=f"account-{user_id}",
        nickname=saved.nickname,
        color=saved.color,
        avatar=Avatar(style=saved.avatar_style, seed=saved.avatar_seed),
        user_id=user_id,
    )


@database_sync_to_async
def record_results(game_id: str, outcomes: dict[int, bool]) -> None:
    """One more game played (and won, for placement 1) per account, in one transaction.

    Accounts deleted since the game started are skipped.
    """
    with transaction.atomic():
        existing = set(User.objects.filter(pk__in=outcomes).values_list("pk", flat=True))
        for user_id, won in outcomes.items():
            if user_id not in existing:
                continue
            PlayerStats.objects.get_or_create(user_id=user_id, game_id=game_id)
            PlayerStats.objects.filter(user_id=user_id, game_id=game_id).update(
                played=F("played") + 1, wins=F("wins") + int(won)
            )
    logger.info("Stats updated: game=%s accounts=%s", game_id, len(outcomes))
