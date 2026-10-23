"""Name It Survival views. Votes stay secret until the challenge closes."""

from typing import TYPE_CHECKING, Any

from games.constants import NAMEIT_CHALLENGE_WINDOW_MS

if TYPE_CHECKING:
    from games.name_it import NameItState


def build_view(state: "NameItState", player_id: str) -> dict[str, Any]:
    """What `player_id` may see: everything public, plus their own vote status."""
    answer = state.used[-1] if state.used else None
    can_challenge = (
        state.phase == "turn"
        and state.window_until is not None
        and answer is not None
        and player_id in state.alive
        and player_id != answer["playerId"]
    )
    return {
        "phase": state.phase,
        "topic": state.topic,
        "topicChooserId": state.chooser if state.phase == "topicSelect" else None,
        "isTopicChooser": state.phase == "topicSelect" and player_id == state.chooser,
        "suggestions": list(state.suggestions) if state.phase == "topicSelect" else [],
        "topicDeadline": state.topic_deadline,
        "order": list(state.order),
        "alive": list(state.alive),
        "eliminated": list(state.eliminated),
        "currentPlayerId": state.current,
        "isYourTurn": state.phase == "turn" and player_id == state.current,
        "turnDeadline": state.turn_deadline,
        "pausedMs": state.paused_ms,
        "used": [{"playerId": u["playerId"], "text": u["text"]} for u in state.used],
        "challengeWindow": (
            {"answerIndex": len(state.used) - 1, "until": state.window_until}
            if state.window_until is not None
            else None
        ),
        "challengeWindowMs": NAMEIT_CHALLENGE_WINDOW_MS,
        "canChallenge": can_challenge,
        "challenge": _challenge_view(state, player_id),
        "lastElimination": dict(state.last_elimination) if state.last_elimination else None,
        "settings": dict(state.settings),
    }


def _challenge_view(state: "NameItState", player_id: str) -> dict[str, Any] | None:
    challenge = state.challenge
    if state.phase != "challenge" or challenge is None:
        return None
    return {
        "answerIndex": challenge["answerIndex"],
        "answererId": challenge["answererId"],
        "challengerId": challenge["challengerId"],
        "text": state.used[challenge["answerIndex"]]["text"],
        "deadline": challenge["deadline"],
        "voterIds": list(challenge["voters"]),
        "votedCount": len(challenge["votes"]),
        "canVote": player_id in challenge["voters"] and player_id not in challenge["votes"],
        "hasVoted": player_id in challenge["votes"],
    }
