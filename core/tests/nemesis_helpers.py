"""Shared helpers for the Nemesis tests: accounts, auth headers and eligible players."""

import itertools
from datetime import timedelta

from django.contrib.auth.models import User
from django.utils import timezone

from accounts import services as account_services
from accounts.models import PlayerStats
from accounts.tokens import issue_token
from games.constants import NEMESIS_MIN_ACCOUNT_AGE_HOURS, NEMESIS_MIN_GAMES, PLAYER_COLORS
from nemesis.models import IdVerification
from rooms.models_types import Avatar

_names = itertools.count(1)
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64


def account_user(*, eligible: bool = False, staff: bool = False) -> User:
    """A registered player; `eligible` adds account age, games played and an approved ID."""
    n = next(_names)
    user = account_services.create_account(
        f"nem_{n}",
        "correct horse battery",
        f"Nem{n}",
        PLAYER_COLORS[0],
        Avatar("cutouts", f"s{n}"),
        {},
    )
    if staff:
        user.is_staff = True
        user.save(update_fields=["is_staff"])
    if eligible:
        make_eligible(user)
    return user


def make_eligible(user: User, *, approved_id: bool = True) -> None:
    age = timedelta(hours=NEMESIS_MIN_ACCOUNT_AGE_HOURS + 1)
    User.objects.filter(pk=user.pk).update(date_joined=timezone.now() - age)
    user.refresh_from_db()
    PlayerStats.objects.update_or_create(
        user=user, game_id="rps", defaults={"played": NEMESIS_MIN_GAMES, "wins": 1}
    )
    if approved_id:
        IdVerification.objects.create(
            user=user,
            id_type="passport",
            full_name="Ama Mensah",
            id_number_hash=f"hash-{user.pk}",
            id_number_last4="1234",
            status=IdVerification.Status.APPROVED,
            attempt_number=1,
        )


def auth(user: User) -> dict[str, str]:
    return {"HTTP_AUTHORIZATION": f"Bearer {issue_token(user.pk)}"}
