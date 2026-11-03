"""Brag coin stakes on games between friends (PROTOCOL.md 17). Mixed into RoomManager.

The host sets a stake (BRAG_STAKES) in the lobby; each registered player joins or sits out.
The game is staked when more than half of the seated players joined. Then the joiners who can
pay play and everyone else sits that game out (like a locked guest); guests never stake. Stakes
are held when the game starts; placement 1 takes the whole pot (a tie for first splits it, and a
tie of everyone gets their stake back); a game that ends without results refunds everyone.
Methods here expect the caller to hold `room.lock`.
"""

from collections.abc import Awaitable, Callable
from typing import Any

from brag.models import BragEntry
from brag.services import BragStore
from games.constants import BRAG_POT_FEE_PERCENT, BRAG_STAKES
from rooms.models_types import Player, Room, RoomError


def _needed(seated: int) -> int:
    """Joiners needed for a majority of `seated` players."""
    return seated // 2 + 1


class StakesMixin:
    """Requires the RoomManager attributes and the GameFlow mixin."""

    brag_store: BragStore
    send: Callable[[str, dict[str, Any]], Awaitable[None]]

    # ----- requests -------------------------------------------------------------------

    async def set_stake(self, code: str | None, player_id: str | None, amount: Any) -> None:
        """Host sets the stake (0 clears it). Everyone else chooses again; the host is in."""
        room = self._room(code)
        async with room.lock:
            host = self._member(room, player_id)
            self._require_host(room, host)
            self._require_lobby(room)
            if type(amount) is not int or (amount != 0 and amount not in BRAG_STAKES):
                raise RoomError("INVALID_ACTION", "Pick one of the stake amounts.")
            if amount and host.user_id is None:
                raise RoomError("REGISTERED_ONLY", "Brag coins are for registered players.")
            if amount:
                await self._require_coins(host, amount)
            if room.stake == amount:
                return
            room.stake = amount
            for player in room.players:
                player.stake_choice = None
            host.stake_choice = True if amount else None
            room.last_activity = self.clock()
            self._reset_ready(room)
            await self._broadcast_room(room)
            await self._room_event(room, "stake_changed", host, {"amount": amount})

    async def stake_choice(self, code: str | None, player_id: str | None, join: Any) -> None:
        """A registered player joins the stake (if they can pay) or sits this round out."""
        room = self._room(code)
        async with room.lock:
            player = self._member(room, player_id)
            self._require_lobby(room)
            if not isinstance(join, bool):
                raise RoomError("INVALID_ACTION", "join must be true or false.")
            if not room.stake:
                raise RoomError("INVALID_ACTION", "This round has no stake.")
            if player.user_id is None:
                raise RoomError("REGISTERED_ONLY", "Brag coins are for registered players.")
            if join:
                await self._require_coins(player, room.stake)
            player.stake_choice = join
            room.last_activity = self.clock()
            await self._broadcast_room(room)

    async def _require_coins(self, player: Player, amount: int) -> None:
        assert player.user_id is not None
        have = await self.brag_store.balance(player.user_id)
        if have is None or have < amount:
            raise RoomError(
                "NOT_ENOUGH_BRAG",
                f"You need {amount} Brag coins for this stake.",
                {"balance": have or 0, "stake": amount},
            )

    # ----- game start and end ----------------------------------------------------------

    def _stake_sitouts(self, room: Room, everyone: list[Player], min_players: int) -> set[str]:
        """Players who sit a staked game out; STAKE_NOT_AGREED without a majority."""
        joiners = [p for p in everyone if p.user_id is not None and p.stake_choice is True]
        needed = _needed(len(everyone))
        if len(joiners) < needed or len(joiners) < min_players:
            raise RoomError(
                "STAKE_NOT_AGREED",
                f"{len(joiners)} of {len(everyone)} players joined the stake; "
                f"{max(needed, min_players)} must join, or remove the stake.",
                {"joined": len(joiners), "needed": max(needed, min_players)},
            )
        return {p.id for p in everyone if p not in joiners}

    async def _take_stakes(self, room: Room, seated: list[Player], game_id: str) -> set[str]:
        """Hold every seated player's stake. Returns those who could not pay (now sitting out)."""
        room.stake_round += 1
        ref = f"{room.code}#{room.stake_round}"
        room.staked, room.stake_result = {}, None
        short = set()
        for player in seated:
            assert player.user_id is not None
            if await self.brag_store.hold_stake(player.user_id, room.stake, game_id, ref):
                room.staked[player.id] = player.user_id
            else:
                short.add(player.id)
        return short

    async def _refund_stakes(self, room: Room, game_id: str) -> None:
        """A staked game ended without a winner: every stake goes back."""
        if not room.staked:
            return
        ref = f"{room.code}#{room.stake_round}"
        for user_id in room.staked.values():
            await self.brag_store.credit(
                user_id, room.stake, BragEntry.Kind.STAKE_REFUND, game_id, ref
            )
        room.stake_result = {"pot": 0, "refunded": True, "winners": [], "each": room.stake}
        room.staked = {}

    async def _settle_stakes(self, room: Room, game_id: str, results: list[Any]) -> None:
        """Placement 1 takes the pot (split on a tie); a tie of everyone is a refund."""
        if not room.staked:
            return
        staked = room.staked
        winners = [
            r["player_id"] for r in results if r["placement"] == 1 and r["player_id"] in staked
        ]
        if not winners or len(winners) == len(staked):
            await self._refund_stakes(room, game_id)
            return
        ref = f"{room.code}#{room.stake_round}"
        pot = room.stake * len(staked)
        prize = pot - pot * BRAG_POT_FEE_PERCENT // 100
        each, extra = divmod(prize, len(winners))
        for i, pid in enumerate(winners):
            share = each + (extra if i == 0 else 0)
            await self.brag_store.credit(staked[pid], share, BragEntry.Kind.POT_WIN, game_id, ref)
        room.stake_result = {"pot": pot, "refunded": False, "winners": winners, "each": each}
        room.staked = {}
