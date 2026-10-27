"""Hangman "not a real word" challenge. Votes stay secret until the vote closes.

After a played round, any guesser may flag the word within HANGMAN_FLAG_WINDOW_MS. Every
guesser (never the setter) is a voter; the flagger's vote counts as Invalid automatically.
The flag is upheld only by a strict majority of all voters voting Invalid, so ties, silence
and absent voters keep the word valid. Upheld: the setter earns 0 for the round and the
guessers share the full HANGMAN_POT. Flagging needs FLAG_MIN_PLAYERS (a neutral voter).
"""

from typing import TYPE_CHECKING, Any

from games.base import GameError, GameEvent
from games.constants import HANGMAN_POT, HANGMAN_VOTE_MS

if TYPE_CHECKING:
    from games.hangman import HangmanState

FLAG_MIN_PLAYERS = 3


def start_flag(state: "HangmanState", flagger: str, now: float) -> list[GameEvent]:
    state.phase, state.flag_until = "flagVote", None
    state.deadline = now + HANGMAN_VOTE_MS
    state.flag = {"flaggerId": flagger, "voters": state.guessers(), "votes": {flagger: False}}
    return [{"kind": "wordFlagged", "data": {"round": state.round_index + 1, "flaggerId": flagger}}]


def vote(state: "HangmanState", player_id: str, valid: Any, now: float) -> list[GameEvent]:
    flag = state.flag
    if state.phase != "flagVote" or flag is None:
        raise GameError("INVALID_ACTION", "There is no vote right now.")
    if player_id not in flag["voters"]:
        raise GameError("INVALID_ACTION", "You don't vote on this word.")
    if player_id in flag["votes"]:
        raise GameError("INVALID_ACTION", "You already voted.")
    if not isinstance(valid, bool):
        raise GameError("INVALID_ACTION", "Vote valid: true or false.")
    flag["votes"][player_id] = valid
    if len(flag["votes"]) == len(flag["voters"]):
        return close_vote(state)
    return []


def drop_voter(state: "HangmanState", player_id: str) -> list[GameEvent]:
    """A guesser forfeited mid-vote: their vote and seat in the vote go, then recount."""
    flag = state.flag
    assert flag is not None
    if player_id not in flag["voters"]:
        return []
    flag["voters"] = [v for v in flag["voters"] if v != player_id]
    flag["votes"].pop(player_id, None)
    if len(flag["votes"]) == len(flag["voters"]):
        return close_vote(state)
    return []


def close_vote(state: "HangmanState") -> list[GameEvent]:
    """Decide the flag and, if upheld, move the round's pot to the guessers."""
    flag = state.flag
    assert flag is not None
    votes = list(flag["votes"].values())
    invalid, valid = votes.count(False), votes.count(True)
    upheld = bool(flag["voters"]) and invalid * 2 > len(flag["voters"])
    flag["upheld"] = upheld
    if upheld:
        guessers = state.guessers()
        new_award = {state.setter: 0.0, **dict.fromkeys(guessers, HANGMAN_POT / len(guessers))}
        for pid in set(state.award) | set(new_award):
            state.scores[pid] += new_award.get(pid, 0.0) - state.award.get(pid, 0.0)
        state.award = new_award
    data = {
        "round": state.round_index + 1,
        "setterId": state.setter,
        "word": state.word,
        "flaggerId": flag["flaggerId"],
        "votes": dict(flag["votes"]),
        "validVotes": valid,
        "invalidVotes": invalid,
        "upheld": upheld,
        "award": {pid: round(pts, 2) for pid, pts in state.award.items()},
    }
    return [{"kind": "flagResult", "data": data}]


def flag_view(state: "HangmanState", player_id: str) -> dict[str, Any] | None:
    """The open vote, without anyone's vote but your own status."""
    flag = state.flag
    if state.phase != "flagVote" or flag is None:
        return None
    return {
        "flaggerId": flag["flaggerId"],
        "deadline": state.deadline,
        "voterIds": list(flag["voters"]),
        "votedCount": len(flag["votes"]),
        "canVote": player_id in flag["voters"] and player_id not in flag["votes"],
        "hasVoted": player_id in flag["votes"],
    }
