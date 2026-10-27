"""Tell the live hub (social.hub) about changes made by HTTP views and other database code.

Safe from any thread; nothing happens while no account is connected. Call after the change
is saved.
"""

from typing import Any

from accounts.models import Profile


def _call(method: str, *args: Any) -> None:
    from rooms import manager as manager_module  # looked up at call time so tests can swap it

    manager_module.manager.social.call_soon(method, *args)


def _who(profile: Profile) -> dict[str, Any]:
    return {"userId": profile.user_id, "tag": profile.tag, "nickname": profile.nickname}


def request_sent(to_user_id: int, request: dict[str, Any]) -> None:
    _call("request_sent", to_user_id, request)


def friends_made(a: Profile, b: Profile) -> None:
    _call("friends_made", _who(a), _who(b))


def friends_removed(a: Profile, b: Profile) -> None:
    _call("friends_removed", _who(a), _who(b))


def blocked(a_id: int, b_id: int) -> None:
    _call("blocked", a_id, b_id)


def mode_changed(user_id: int, mode: str) -> None:
    _call("mode_changed", user_id, mode)


def account_gone(user_id: int) -> None:
    """The account was disabled or deleted."""
    _call("account_gone", user_id)
