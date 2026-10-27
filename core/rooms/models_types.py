"""In-memory room and player records, plus their wire (camelCase) serialization."""

import asyncio
from dataclasses import dataclass, field
from typing import Any, Literal

from games.scoring import ScoredResult

RoomStatus = Literal["lobby", "playing", "between_rounds", "finished"]
EndReason = Literal["completed", "forfeit", "host_ended"]


class RoomError(Exception):
    """A rejected room request. `code` is a protocol error code such as NOT_HOST."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


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
    """

    id: str
    profile_id: str
    nickname: str
    color: str
    avatar: Avatar
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

    @property
    def type(self) -> str:
        """ "registered" for a seat held by an account, else "guest"."""
        return "registered" if self.user_id is not None else "guest"

    def to_public(self) -> dict[str, Any]:
        """The `Player` wire type."""
        return {
            "id": self.id,
            "type": self.type,
            "nickname": self.nickname,
            "color": self.color,
            "avatar": self.avatar.to_public(),
            "online": self.online,
            "offlineSince": self.offline_since,
            "inGame": self.in_game,
            "joinedAt": self.joined_at,
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

    def player(self, player_id: str) -> Player | None:
        """Find a seated player by id."""
        return next((p for p in self.players if p.id == player_id), None)

    def seated(self) -> list[Player]:
        """Players who have not left (left players stay seated until the game ends)."""
        return [p for p in self.players if not p.left]

    def host(self) -> Player | None:
        """The current host's seat."""
        return self.player(self.host_id)

    def to_public(self) -> dict[str, Any]:
        """The `RoomPublic` wire type. Contains no tokens, channels or game state.

        Players who left mid-game stay listed (offline) until the game ends, so game
        views can still refer to them.
        """
        players = self.players
        ids = {p.id for p in players}
        return {
            "code": self.code,
            "hostId": self.host_id,
            "status": self.status,
            "players": [p.to_public() for p in players],
            "selectedGame": self.selected_game,
            "settings": dict(self.settings),
            "scoreboard": {pid: pts for pid, pts in self.scoreboard.items() if pid in ids},
            "wins": {pid: n for pid, n in self.wins.items() if pid in ids},
            "endReason": self.end_reason,
        }


def result_to_public(result: ScoredResult) -> dict[str, Any]:
    """The `GameResult` wire type: the game's placement and raw score, plus session points."""
    return {
        "playerId": result["player_id"],
        "placement": result["placement"],
        "score": result["score"],
        "points": result["points"],
    }
