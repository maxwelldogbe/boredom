"""Account models, database settings and auth-related settings."""

import pytest
from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from accounts.models import PlayerStats, Profile
from games.constants import PLAYER_COLORS

pytestmark = pytest.mark.django_db


def make_user(username: str = "sam") -> User:
    user = User.objects.create_user(username=username, password="correct horse battery")
    Profile.objects.create(
        user=user,
        nickname="Sam",
        color=PLAYER_COLORS[0],
        avatar_style="cutouts",
        avatar_seed="ab12",
    )
    return user


def test_profile_and_stats_belong_to_user() -> None:
    user = make_user()
    PlayerStats.objects.create(user=user, game_id="rps", played=3, wins=1)
    assert user.profile.nickname == "Sam"
    assert list(user.stats.values_list("game_id", "played", "wins")) == [("rps", 3, 1)]


def test_stats_unique_per_user_and_game() -> None:
    user = make_user()
    PlayerStats.objects.create(user=user, game_id="rps")
    with pytest.raises(IntegrityError), transaction.atomic():
        PlayerStats.objects.create(user=user, game_id="rps")


def test_stats_wins_never_exceed_played() -> None:
    user = make_user()
    with pytest.raises(IntegrityError), transaction.atomic():
        PlayerStats.objects.create(user=user, game_id="rps", played=1, wins=2)


def test_deleting_user_deletes_profile_and_stats() -> None:
    user = make_user()
    PlayerStats.objects.create(user=user, game_id="rps", played=1)
    user.delete()
    assert not Profile.objects.exists()
    assert not PlayerStats.objects.exists()


def test_password_min_length_comes_from_constants() -> None:
    with pytest.raises(ValidationError):
        validate_password("Zq7#kw2")  # 7 characters
    validate_password("Zq7#kw2!")  # 8 characters


def test_cors_allows_authorization_header() -> None:
    assert "authorization" in settings.CORS_ALLOW_HEADERS


def test_database_defaults_to_sqlite() -> None:
    assert settings.DATABASES["default"]["ENGINE"] == "django.db.backends.sqlite3"
