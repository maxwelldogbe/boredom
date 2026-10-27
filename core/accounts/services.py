"""Account operations shared by the HTTP views (and later the WebSocket and admin)."""

import logging
from datetime import datetime, timedelta
from typing import Any

from django.contrib.auth.models import User
from django.db import transaction
from django.utils import timezone

from accounts.models import PlayerStats, Profile
from accounts.tags import issue_tag
from analytics.models import DELETED_NICKNAME, ActivityEvent, GameParticipation
from analytics.recorder import recorder
from games import registry
from games.constants import AVATAR_CHANGE_DAYS, STATS_MAX_IMPORT_GAMES
from rooms.avatars import SystemAvatarRng, assign_avatar, validate_avatar
from rooms.models_types import Avatar, RoomError
from rooms.models_types import Profile as RoomProfile
from social import notify

logger = logging.getLogger("accounts")

avatar_rng = SystemAvatarRng()


def claim_avatar(raw: Any, nickname: str, color: str) -> Avatar:
    """The guest's avatar if valid (kept until the player changes it), else a fresh random one."""
    if raw is not None:
        try:
            return validate_avatar(raw)
        except RoomError:
            pass
    return assign_avatar(RoomProfile(id="account", nickname=nickname, color=color), avatar_rng)


def clean_imported_stats(raw: Any) -> dict[str, tuple[int, int]]:
    """Guest stats worth keeping, as {game_id: (played, wins)}; anything doubtful gives {}.

    Accepted only when every entry is a known game with integers 0 <= wins <= played and
    the total played is at most STATS_MAX_IMPORT_GAMES. They are for fun only.
    """
    by_game = raw.get("byGame") if isinstance(raw, dict) else None
    if not isinstance(by_game, dict):
        return {}
    known = registry.all_games()
    cleaned: dict[str, tuple[int, int]] = {}
    for game_id, entry in by_game.items():
        if game_id not in known or not isinstance(entry, dict):
            return {}
        played, wins = entry.get("played"), entry.get("wins")
        if not all(type(n) is int for n in (played, wins)) or not 0 <= wins <= played:
            return {}
        if played:
            cleaned[game_id] = (played, wins)
    if sum(played for played, _ in cleaned.values()) > STATS_MAX_IMPORT_GAMES:
        return {}
    return cleaned


def create_account(
    username: str, password: str, nickname: str, color: str, avatar: Avatar, stats: dict
) -> User:
    """Create the user, profile and imported stats together. IntegrityError if taken."""
    with transaction.atomic():
        user = User.objects.create_user(username=username, password=password)
        Profile.objects.create(
            user=user,
            nickname=nickname,
            color=color,
            avatar_style=avatar.style,
            avatar_seed=avatar.seed,
            tag=issue_tag(username),
        )
        PlayerStats.objects.bulk_create(
            PlayerStats(user=user, game_id=game_id, played=played, wins=wins)
            for game_id, (played, wins) in stats.items()
        )
    logger.info("Account created: user=%s", user.pk)
    recorder.record_event("signup", user_id=user.pk)
    return user


def delete_account(user: User) -> None:
    """The one deletion path (public endpoint and admin): anonymise, then delete.

    The person's game participations and activity events are kept, so every total stays
    correct, but lose their link to the account and their nickname snapshot. The user, the
    saved profile and the stats are then deleted, and with them (by cascade) the account's
    friendships, friend requests and blocks. Reports by or about the account are kept with
    the account link set to null; the reported nickname snapshot stays.
    """
    user_id = user.pk
    with transaction.atomic():
        GameParticipation.objects.filter(user=user).update(user=None, nickname=DELETED_NICKNAME)
        ActivityEvent.objects.filter(user=user).update(user=None)
        user.delete()
    notify.account_gone(user_id)
    logger.info("Account deleted: user=%s", user_id)
    recorder.record_event("account_deleted")


def avatar_locked_until(profile: Profile, now: datetime) -> datetime | None:
    """When the next avatar change is allowed, or None if it is allowed now."""
    if profile.avatar_changed_at is None:
        return None
    until = profile.avatar_changed_at + timedelta(days=AVATAR_CHANGE_DAYS)
    return until if until > now else None


def ms(moment: datetime) -> int:
    return int(moment.timestamp() * 1000)


def public_profile(profile: Profile) -> dict[str, Any]:
    """The owner's own saved profile (only ever sent to the account holder)."""
    locked_until = avatar_locked_until(profile, timezone.now())
    return {
        "username": profile.user.username,
        "nickname": profile.nickname,
        "color": profile.color,
        "avatar": {"style": profile.avatar_style, "seed": profile.avatar_seed},
        "type": "registered",
        "createdAt": ms(profile.created_at),
        # Epoch ms of the next allowed avatar change; null when a change is allowed now.
        "avatarLockedUntil": ms(locked_until) if locked_until else None,
    }


def public_stats(user: User) -> dict[str, Any]:
    """The account's stats in the client's Stats shape."""
    by_game = {s.game_id: {"played": s.played, "wins": s.wins} for s in user.stats.all()}
    return {
        "gamesPlayed": sum(g["played"] for g in by_game.values()),
        "wins": sum(g["wins"] for g in by_game.values()),
        "byGame": by_game,
    }
