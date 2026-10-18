"""In-memory room and player records, plus their wire (camelCase) serialization."""

import asyncio
from dataclasses import dataclass, field
from typing import Any, Literal

from games.base import GameResult

RoomStatus = Literal["lobby", "playing", "between_rounds", "finished"]


class RoomError(Exception):
    """A rejected room request. `code` is a protocol error code such as NOT_HOST."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class Profile:
    """A validated, sanitized client profile. Client-supplied stats are never kept."""

    id: str
    nickname: str
    emoji: str
    color: str


@dataclass
class Player:
    """A seat in a room. `token` reclaims the seat; it is never sent to other players."""

    id: str
    profile_id: str
    nickname: str
    emoji: str
    color: str
    joined_at: float
    token: str
    channel: str | None = None
    online: bool = True
    offline_since: float | None = None
    left: bool = False

    def to_public(self) -> dict[str, Any]:
        """The `Player` wire type."""
        return {
            "id": self.id,
            "profileId": self.profile_id,
            "nickname": self.nickname,
            "emoji": self.emoji,
            "color": self.color,
            "online": self.online,
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
    scoreboard: dict[str, int] = field(default_factory=dict)
    wins: dict[str, int] = field(default_factory=dict)
    game_id: str | None = None
    game_state: Any = None
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    timer_task: asyncio.Task[None] | None = None
    host_task: asyncio.Task[None] | None = None

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
        }


def result_to_public(result: GameResult) -> dict[str, Any]:
    """The `GameResult` wire type."""
    return {
        "playerId": result["player_id"],
        "placement": result["placement"],
        "points": result["points"],
    }
