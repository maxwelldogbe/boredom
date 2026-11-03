"""In-memory room and player records, plus their wire (camelCase) serialization."""

import asyncio
import random
from dataclasses import dataclass, field
from typing import Any, Literal

from games import availability
from games.constants import REGISTERED_ONLY_GAMES
from games.scoring import ScoredResult

RoomStatus = Literal["lobby", "playing", "between_rounds", "finished"]
EndReason = Literal["completed", "forfeit", "host_ended"]


class RoomError(Exception):
    """A rejected room request. `code` is a protocol error code such as NOT_HOST."""

    def __init__(self, code: str, message: str, data: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data  # extra error details sent as `error.data` (e.g. GUEST_LIMIT)


@dataclass(frozen=True)
class Avatar:
    """A DiceBear avatar: a style and a seed. The server never builds or sends image URLs."""

    style: str
    seed: str

    def to_public(self) -> dict[str, str]:
        """The `Avatar` wire type."""
        return {"style": self.style, "seed": self.seed}


@dataclass(frozen=True)
class Profile:
    """A validated, sanitized client profile, or a registered account's saved profile.

    Client-supplied stats are never kept. `avatar` is what the client sent (validated);
    guests' avatars are ignored at seat creation. `user_id` is set only for an account
    loaded from a valid authToken, and then `avatar` is the account's saved avatar.
    """

    id: str
    nickname: str
    color: str
    avatar: Avatar | None = None
    user_id: int | None = None


@dataclass
class Player:
    """A seat in a room. `token` reclaims the seat; it is never sent to other players.

    `profile_id` and `user_id` stay on the server: room:state only exposes `type`.
    A solo room's bot (`bot`) has no account, token, channel or avatar.
    """

    id: str
    profile_id: str
    nickname: str
    color: str
    avatar: Avatar | None
    joined_at: float
    token: str
    channel: str | None = None
    online: bool = True
    offline_since: float | None = None
    user_id: int | None = None
    guest_key: str = ""  # pseudonymous id for activity records (guests only)
    left: bool = False
    in_game: bool = True  # False once forfeited from the running game (quit, left, offline)
    offline_notified: bool = False  # a player_offline event went out for this disconnect
    ready: bool = False  # lobby ready check; never counted for the host
    reacted_at: float | None = None  # last accepted room:react, for the cooldown
    locked: bool = False  # a guest out of free games (from the quota at the last game start)
    bot: bool = False  # the bot of a solo room
    stake_choice: bool | None = None  # Brag stake: True joins, False sits out, None undecided

    @property
    def type(self) -> str:
        """ "registered" for a seat held by an account, "bot" for a solo bot, else "guest"."""
        if self.bot:
            return "bot"
        return "registered" if self.user_id is not None else "guest"

    def to_public(self, host_id: str = "", registered_only: bool = False) -> dict[str, Any]:
        """The `Player` wire type. `ready` is always false for the host.

        `registered_only`: the room's game is for registered players, so a guest is blocked.
        """
        return {
            "id": self.id,
            "type": self.type,
            "nickname": self.nickname,
            "color": self.color,
            "avatar": self.avatar.to_public() if self.avatar is not None else None,
            "online": self.online,
            "offlineSince": self.offline_since,
            "inGame": self.in_game,
            "joinedAt": self.joined_at,
            "ready": self.ready and self.id != host_id,
            "locked": self.locked and self.user_id is None,
            "registeredOnlyBlocked": registered_only and self.user_id is None and not self.bot,
            "bot": self.bot,
            "stakeChoice": None
            if self.stake_choice is None
            else ("in" if self.stake_choice else "out"),
        }


@dataclass
class Room:
    """A room and, while playing, its active game. Mutate only while holding `lock`."""

    code: str
    host_id: str
    created_at: float
    last_activity: float
    status: RoomStatus = "lobby"
    players: list[Player] = field(default_factory=list)
    selected_game: str | None = None
    settings: dict[str, Any] = field(default_factory=dict)
    scoreboard: dict[str, float] = field(default_factory=dict)
    wins: dict[str, int] = field(default_factory=dict)
    game_id: str | None = None
    game_state: Any = None
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    timer_task: asyncio.Task[None] | None = None
    host_task: asyncio.Task[None] | None = None
    game_started_at: float | None = None
    game_players: list[str] = field(default_factory=list)  # who started the running game
    forfeits: dict[str, float] = field(default_factory=dict)  # player -> forfeit time
    end_reason: EndReason | None = None
    notice_tasks: dict[str, asyncio.Task[None]] = field(default_factory=dict)
    forfeit_tasks: dict[str, asyncio.Task[None]] = field(default_factory=dict)
    used_content: dict[str, frozenset[str]] = field(default_factory=dict)  # game id -> keys
    # Solo rooms (rooms/solo.py): one player and a bot, private to `solo_owner`.
    solo: bool = False
    solo_owner: int | None = None  # user id
    solo_variant: dict[str, Any] = field(default_factory=dict)  # {"difficulty": ...}
    solo_first: str | None = None  # first mover of the latest solo game
    solo_result: dict[str, Any] | None = None  # soloResult of the finished game
    bot_rng: random.Random | None = None
    bot_seq: int = 0  # bumped on every state change; a bot task acts only on its own number
    bot_continuing: bool = False  # the bot's own move is being applied (it may keep the turn)
    bot_task: asyncio.Task[None] | None = None
    idle_task: asyncio.Task[None] | None = None  # closes the solo room while nobody is connected
    # Brag coin stakes (rooms/stakes.py): the amount the host set (0: none), who paid into the
    # running game's pot (player id -> user id), and how the last staked game was settled.
    stake: int = 0
    staked: dict[str, int] = field(default_factory=dict)
    stake_round: int = 0
    stake_result: dict[str, Any] | None = None

    def player(self, player_id: str) -> Player | None:
        """Find a seated player by id."""
        return next((p for p in self.players if p.id == player_id), None)

    def seated(self) -> list[Player]:
        """Players who have not left (left players stay seated until the game ends)."""
        return [p for p in self.players if not p.left]

    def bot(self) -> Player | None:
        """The bot's seat in a solo room."""
        return next((p for p in self.players if p.bot), None)

    def host(self) -> Player | None:
        """The current host's seat."""
        return self.player(self.host_id)

    def registered_only(self) -> bool:
        """True while the selected (or running) game is for registered players only."""
        running = self.game_id if self.status == "playing" else None
        return bool({self.selected_game, running} & REGISTERED_ONLY_GAMES)

    def ready_check(self) -> dict[str, int] | None:
        """Ready count among online non-host players; None while no game is selected."""
        if self.selected_game is None:
            return None
        voters = [
            p
            for p in self.seated()
            if p.online
            and p.id != self.host_id
            and not (p.locked and p.user_id is None)
            and not (self.registered_only() and p.user_id is None)
        ]
        return {"count": sum(p.ready for p in voters), "total": len(voters)}

    def to_public(self, viewer: "Player | None" = None) -> dict[str, Any]:
        """The `RoomPublic` wire type. Contains no tokens, channels or game state.

        Players who left mid-game stay listed (offline) until the game ends, so game
        views can still refer to them. A guest `viewer` never learns a registered-only
        game: `selectedGame` and `settings` are null for them while one is selected.
        """
        players = self.players
        ids = {p.id for p in players}
        registered_only = self.registered_only()
        hidden = registered_only and viewer is not None and viewer.user_id is None
        return {
            "code": self.code,
            "hostId": self.host_id,
            "status": self.status,
            "players": [p.to_public(self.host_id, registered_only) for p in players],
            "selectedGame": None if hidden else self.selected_game,
            "settings": None if hidden else dict(self.settings),
            "scoreboard": {pid: pts for pid, pts in self.scoreboard.items() if pid in ids},
            "wins": {pid: n for pid, n in self.wins.items() if pid in ids},
            "endReason": self.end_reason,
            "readyCheck": self.ready_check(),
            "disabledGames": sorted(availability.disabled()),
            "solo": self.solo,
            "soloVariant": dict(self.solo_variant) if self.solo else None,
            "stake": self.stake,
            "staked": list(self.staked),
            "pot": self.stake * len(self.staked) if self.staked else 0,
            "stakeResult": dict(self.stake_result) if self.stake_result else None,
        }


def result_to_public(result: ScoredResult) -> dict[str, Any]:
    """The `GameResult` wire type: the game's placement and raw score, plus session points."""
    return {
        "playerId": result["player_id"],
        "placement": result["placement"],
        "score": result["score"],
        "points": result["points"],
    }
