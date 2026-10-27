"""Friends, blocks and reports: the rules shared by the HTTP API and the WebSocket.

Nothing returned here contains a login username, user id, profile id or email; players are
named by their public tag. A block is never revealed: requests to (or from) a blocked or
disabled account answer exactly like a normal request but create nothing.
"""

import unicodedata
from datetime import timedelta
from typing import Any

from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone

from accounts.me import iso
from accounts.me import stats as account_stats
from accounts.models import Profile
from accounts.ratelimit import KeyedRateLimiter
from accounts.tags import ensure_tag
from games.constants import (
    FRIEND_REQUESTS_PER_HOUR,
    MAX_FRIENDS,
    MAX_PENDING_INCOMING,
    MAX_PENDING_OUTGOING,
    REPORT_DUPLICATE_WINDOW_HOURS,
    REPORT_NOTE_MAX,
    REPORT_REASONS,
    REPORTS_PER_DAY,
    TAG_ALPHABET,
    TAG_LENGTH,
)
from social import notify, presence
from social.errors import SocialError
from social.models import Block, FriendRequest, Friendship, Report

request_limiter = KeyedRateLimiter(FRIEND_REQUESTS_PER_HOUR, window=3600.0)

STATUS_ORDER = {s: i for i, s in enumerate(presence.STATUSES)}


NOT_FOUND = "We couldn't find a player with that tag."


# ----- lookups -----------------------------------------------------------------------------


def normalize_tag(raw: Any) -> str:
    """ "#k7m2qx " -> "K7M2QX". Anything that cannot be a tag raises INVALID_INPUT."""
    if not isinstance(raw, str):
        raise SocialError("INVALID_INPUT", "Enter a tag.", {"tag": "Enter a tag."})
    tag = raw.strip().lstrip("#").strip().upper()
    if len(tag) != TAG_LENGTH or any(ch not in TAG_ALPHABET for ch in tag):
        message = f"A tag is {TAG_LENGTH} letters and numbers, like #K7M2QX."
        raise SocialError("INVALID_INPUT", message, {"tag": message})
    return tag


def profile_by_tag(raw: Any) -> Profile:
    """The profile with this tag (active or not), or NOT_FOUND."""
    profile = Profile.objects.select_related("user").filter(tag=normalize_tag(raw)).first()
    if profile is None:
        raise SocialError("NOT_FOUND", NOT_FOUND)
    return profile


def _pair(a: int, b: int) -> tuple[int, int]:
    return (a, b) if a < b else (b, a)


def are_friends(a: int, b: int) -> bool:
    low, high = _pair(a, b)
    return Friendship.objects.filter(user_low_id=low, user_high_id=high).exists()


def blocked_either(a: int, b: int) -> bool:
    return Block.objects.filter(
        Q(blocker_id=a, blocked_id=b) | Q(blocker_id=b, blocked_id=a)
    ).exists()


def blocked_ids(user_id: int) -> set[int]:
    """Everyone `user_id` blocked or was blocked by."""
    rows = Block.objects.filter(Q(blocker_id=user_id) | Q(blocked_id=user_id))
    return {b if a == user_id else a for a, b in rows.values_list("blocker_id", "blocked_id")}


def friend_ids(user_id: int) -> set[int]:
    """Active friends of `user_id` (disabled accounts drop out of every friend list)."""
    rows = Friendship.objects.filter(Q(user_low_id=user_id) | Q(user_high_id=user_id)).filter(
        user_low__is_active=True, user_high__is_active=True
    )
    return {h if lo == user_id else lo for lo, h in rows.values_list("user_low_id", "user_high_id")}


def _friend_count(user_id: int) -> int:
    return Friendship.objects.filter(Q(user_low_id=user_id) | Q(user_high_id=user_id)).count()


def _card(profile: Profile) -> dict[str, Any]:
    return {
        "tag": ensure_tag(profile),
        "nickname": profile.nickname,
        "avatar": {"style": profile.avatar_style, "seed": profile.avatar_seed},
        "color": profile.color,
    }


def _profiles(user_ids) -> dict[int, Profile]:
    rows = Profile.objects.filter(user_id__in=list(user_ids)).select_related("user")
    return {p.user_id: p for p in rows}


# ----- friends list --------------------------------------------------------------------------


def friend_entries(user: User) -> list[dict[str, Any]]:
    """{tag, nickname, avatar, color, status} per friend, online first, then by nickname."""
    entries = [
        {**_card(p), "status": presence.status(p)} for p in _profiles(friend_ids(user.pk)).values()
    ]
    entries.sort(key=lambda e: (STATUS_ORDER[e["status"]], e["nickname"].lower(), e["tag"]))
    return entries


def _request_entry(request: FriendRequest, other: Profile) -> dict[str, Any]:
    return {"requestId": request.pk, **_card(other), "createdAt": iso(request.created_at)}


def overview(user: User) -> dict[str, Any]:
    """GET /api/friends: friends, incoming and outgoing requests, and blocked players."""
    incoming = FriendRequest.objects.filter(to_user=user, from_user__is_active=True)
    outgoing = FriendRequest.objects.filter(from_user=user, to_user__is_active=True)
    incoming = list(incoming.select_related("from_user__profile").order_by("-created_at", "-pk"))
    outgoing = list(outgoing.select_related("to_user__profile").order_by("-created_at", "-pk"))
    blocks = Block.objects.filter(blocker=user).select_related("blocked__profile")
    return {
        "friends": friend_entries(user),
        "incoming": [_request_entry(r, r.from_user.profile) for r in incoming],
        "outgoing": [_request_entry(r, r.to_user.profile) for r in outgoing],
        "blocked": [_card(b.blocked.profile) for b in blocks.order_by("-created_at", "-pk")],
    }


def relationships(user: User) -> dict[int, str]:
    """user id -> friends | requested | incoming, for everyone with a relationship."""
    out: dict[int, str] = {uid: "friends" for uid in friend_ids(user.pk)}
    for uid in FriendRequest.objects.filter(from_user=user).values_list("to_user_id", flat=True):
        out.setdefault(uid, "requested")
    for uid in FriendRequest.objects.filter(to_user=user).values_list("from_user_id", flat=True):
        out.setdefault(uid, "incoming")
    return out


# ----- requests ------------------------------------------------------------------------------


def _make_friends(a: User, b: User) -> None:
    """Turn a pending pair into a friendship (both directions of request removed)."""
    for user in (a, b):
        if _friend_count(user.pk) >= MAX_FRIENDS:
            raise SocialError("LIMIT_REACHED", f"A player can have at most {MAX_FRIENDS} friends.")
    low, high = _pair(a.pk, b.pk)
    FriendRequest.objects.filter(Q(from_user=a, to_user=b) | Q(from_user=b, to_user=a)).delete()
    Friendship.objects.get_or_create(user_low_id=low, user_high_id=high)


def send_request(user: User, target: Profile) -> dict[str, Any]:
    """Ask `target` to be friends. {"status": "requested"} or, if they asked first, "friends".

    Requests to a blocked (either way) or disabled account answer "requested" and create
    nothing, after the same limit checks as a real request.
    """
    other = target.user
    if other.pk == user.pk:
        raise SocialError("SELF", "That's your own tag.")
    if not request_limiter.allow(f"user:{user.pk}"):
        raise SocialError("RATE_LIMITED", "Too many friend requests. Try again later.")
    hidden = not other.is_active or blocked_either(user.pk, other.pk)
    with transaction.atomic():
        if not hidden and are_friends(user.pk, other.pk):
            raise SocialError("ALREADY_FRIENDS", "You're already friends.")
        if not hidden and FriendRequest.objects.filter(from_user=user, to_user=other).exists():
            raise SocialError("ALREADY_REQUESTED", "You already sent a request.")
        crossed = FriendRequest.objects.filter(from_user=other, to_user=user).exists()
        if not hidden and crossed:
            _make_friends(user, other)
    if not hidden and crossed:
        notify.friends_made(user.profile, target)
        return {"status": "friends"}
    with transaction.atomic():
        if _friend_count(user.pk) >= MAX_FRIENDS:
            raise SocialError("LIMIT_REACHED", f"You can have at most {MAX_FRIENDS} friends.")
        if FriendRequest.objects.filter(from_user=user).count() >= MAX_PENDING_OUTGOING:
            message = f"You have {MAX_PENDING_OUTGOING} requests waiting. Cancel some first."
            raise SocialError("LIMIT_REACHED", message)
        if hidden:
            return {"status": "requested"}
        if FriendRequest.objects.filter(to_user=other).count() >= MAX_PENDING_INCOMING:
            raise SocialError("LIMIT_REACHED", "That player can't take more requests right now.")
        try:
            with transaction.atomic():
                created = FriendRequest.objects.create(from_user=user, to_user=other)
        except IntegrityError:
            raise SocialError("ALREADY_REQUESTED", "You already sent a request.") from None
    notify.request_sent(other.pk, _request_entry(created, user.profile))
    return {"status": "requested"}


def _incoming(user: User, request_id: Any) -> FriendRequest:
    """A pending request addressed to `user` from an active account, else NOT_FOUND."""
    found = (
        FriendRequest.objects.select_related("from_user__profile")
        .filter(pk=request_id, to_user=user, from_user__is_active=True)
        .first()
        if isinstance(request_id, int)
        else None
    )
    if found is None:
        raise SocialError("NOT_FOUND", "That request is no longer available.")
    return found


def accept_request(user: User, request_id: Any) -> FriendRequest:
    """Accept an incoming request (recipient only). Returns the consumed request."""
    with transaction.atomic():
        request = _incoming(user, request_id)
        _make_friends(user, request.from_user)
    notify.friends_made(user.profile, request.from_user.profile)
    return request


def decline_request(user: User, request_id: Any) -> None:
    """Decline an incoming request (recipient only). The sender is not told."""
    _incoming(user, request_id).delete()


def cancel_request(user: User, request_id: Any) -> FriendRequest:
    """Cancel one of the user's own outgoing requests."""
    found = (
        FriendRequest.objects.select_related("to_user")
        .filter(pk=request_id, from_user=user)
        .first()
        if isinstance(request_id, int)
        else None
    )
    if found is None:
        raise SocialError("NOT_FOUND", "That request is no longer available.")
    found.delete()
    return found


def remove_friend(user: User, target: Profile) -> None:
    """Unfriend `target`; nobody is told."""
    low, high = _pair(user.pk, target.user_id)
    deleted, _ = Friendship.objects.filter(user_low_id=low, user_high_id=high).delete()
    if not deleted:
        raise SocialError("NOT_FOUND", "That player is not on your friends list.")
    notify.friends_removed(user.profile, target)


def friend_profile(user: User, target: Profile) -> dict[str, Any]:
    """A friend's card, join date and stats. Non-friends get FORBIDDEN."""
    if not target.user.is_active or not are_friends(user.pk, target.user_id):
        raise SocialError("FORBIDDEN", "Only friends can see this profile.")
    return {
        **_card(target),
        "memberSince": iso(target.created_at),
        "stats": account_stats(target.user),
    }


# ----- blocks --------------------------------------------------------------------------------


def block(user: User, target: Profile) -> None:
    """Block `target`: removes any friendship and pending requests both ways, silently."""
    other = target.user
    if other.pk == user.pk:
        raise SocialError("SELF", "You can't block yourself.")
    low, high = _pair(user.pk, other.pk)
    with transaction.atomic():
        Block.objects.get_or_create(blocker=user, blocked=other)
        unfriended, _ = Friendship.objects.filter(user_low_id=low, user_high_id=high).delete()
        FriendRequest.objects.filter(
            Q(from_user=user, to_user=other) | Q(from_user=other, to_user=user)
        ).delete()
    if unfriended:
        notify.friends_removed(user.profile, target)
    notify.blocked(user.pk, other.pk)


def unblock(user: User, target: Profile) -> None:
    deleted, _ = Block.objects.filter(blocker=user, blocked_id=target.user_id).delete()
    if not deleted:
        raise SocialError("NOT_FOUND", "That player is not blocked.")


# ----- reports -------------------------------------------------------------------------------


def clean_note(raw: Any) -> str:
    """The admin-only report note without control or format characters, or INVALID_INPUT."""
    if raw is None:
        return ""
    if not isinstance(raw, str):
        raise SocialError("INVALID_INPUT", "The note must be text.", {"note": "Must be text."})
    note = "".join(" " if ch in "\n\r\t" else ch for ch in raw)
    note = "".join(ch for ch in note if unicodedata.category(ch) not in ("Cc", "Cf")).strip()
    if len(note) > REPORT_NOTE_MAX:
        message = f"Keep the note to {REPORT_NOTE_MAX} characters."
        raise SocialError("INVALID_INPUT", message, {"note": message})
    return note


def clean_reason(raw: Any) -> str:
    if raw not in REPORT_REASONS:
        raise SocialError("INVALID_INPUT", "Pick a reason.", {"reason": "Pick a reason."})
    return raw


def report(
    reporter: User,
    reason: Any,
    note: Any,
    *,
    target: Profile | None = None,
    guest_key: str = "",
    nickname: str = "",
    room_code: str = "",
    game_id: str = "",
) -> None:
    """Report a registered account (`target`) or a guest seat (`guest_key` and `nickname`).

    A repeat report on the same player within REPORT_DUPLICATE_WINDOW_HOURS is merged into
    the reporter's open report (a missing note is filled in). New reports count toward
    REPORTS_PER_DAY.
    """
    reason, note = clean_reason(reason), clean_note(note)
    if target is not None and target.user_id == reporter.pk:
        raise SocialError("SELF", "You can't report yourself.")
    now = timezone.now()
    who = {"reported_user_id": target.user_id} if target else {"reported_guest_key": guest_key}
    window = now - timedelta(hours=REPORT_DUPLICATE_WINDOW_HOURS)
    with transaction.atomic():
        existing = (
            Report.objects.filter(
                reporter=reporter, status=Report.Status.OPEN, created_at__gte=window, **who
            )
            .order_by("-created_at")
            .first()
        )
        if existing is not None:
            if note and not existing.note:
                existing.note = note
                existing.save(update_fields=["note"])
            return
        today = Report.objects.filter(reporter=reporter, created_at__gte=now - timedelta(days=1))
        if today.count() >= REPORTS_PER_DAY:
            raise SocialError("RATE_LIMITED", "You've sent a lot of reports today. Thank you.")
        Report.objects.create(
            reporter=reporter,
            reported_nickname=(target.nickname if target else nickname),
            reason=reason,
            note=note,
            room_code=room_code,
            game_id=game_id,
            **who,
        )
