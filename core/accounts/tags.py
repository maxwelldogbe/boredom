"""Public account tags: TAG_LENGTH characters from TAG_ALPHABET, random, unique forever.

A tag is shown as "#" plus the code. It is not the login username and never contains it.
"""

import secrets

from django.db import IntegrityError, transaction

from accounts.models import Profile, TakenTag
from games.constants import TAG_ALPHABET, TAG_LENGTH

MAX_ATTEMPTS = 50


def random_tag() -> str:
    return "".join(secrets.choice(TAG_ALPHABET) for _ in range(TAG_LENGTH))


def reveals(tag: str, username: str) -> bool:
    """True if the tag equals or contains the username (ignoring case)."""
    return bool(username) and username.upper() in tag.upper()


def issue_tag(username: str) -> str:
    """Reserve a new tag in TakenTag, retrying on collisions. Runs in the caller's transaction."""
    for _ in range(MAX_ATTEMPTS):
        tag = random_tag()
        if reveals(tag, username):
            continue
        try:
            with transaction.atomic():  # a savepoint, so a collision does not spoil the outer one
                TakenTag.objects.create(tag=tag)
        except IntegrityError:
            continue
        return tag
    raise RuntimeError("Could not issue a unique account tag.")


def ensure_tag(profile: Profile) -> str:
    """The profile's tag, assigning one first if it has none (only before the backfill ran)."""
    if profile.tag:
        return profile.tag
    with transaction.atomic():
        locked = Profile.objects.select_for_update().select_related("user").get(pk=profile.pk)
        if not locked.tag:
            locked.tag = issue_tag(locked.user.username)
            locked.save(update_fields=["tag"])
    profile.tag = locked.tag
    return profile.tag
