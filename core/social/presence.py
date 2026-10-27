"""What friends see as a player's status: online, in_lobby, in_game, busy or offline."""

from accounts.models import Profile

STATUSES = ("online", "in_lobby", "in_game", "busy", "offline")


def status(profile: Profile) -> str:
    """The status friends were last told by the live hub (social.hub); offline if none.

    Safe from HTTP threads: one dict lookup on the hub's record of pushed statuses.
    """
    from rooms import manager as manager_module  # looked up at call time so tests can swap it

    if not profile.user.is_active:
        return "offline"
    return manager_module.manager.social.statuses.get(profile.user_id, "offline")
