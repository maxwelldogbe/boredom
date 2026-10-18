# Boredom WebSocket Protocol

> **Status: rooms, RPS, Guess Race complete (phase B3).** The envelope, event names, error codes and room types
> are fixed. Game sections (**B2–B7**) are filled in as each game lands. This file is kept in sync
> with the code; if they ever disagree, report it.
>
> **Changes approved after B0:** `RoomPublic.wins` added; `game:view` carries `serverNow`;
> a game's end is announced with `game:event` kind `gameOver`; mid-game `room:leave` keeps the
> seat (offline) until the game ends.

## 1. Transport

| Item | Value |
| --- | --- |
| WebSocket URL | `ws(s)://<server-host>/ws/` (single endpoint) |
| Origin check | The browser `Origin` host must be in `DJANGO_ALLOWED_HOSTS`, otherwise the socket is closed. |
| Encoding | One JSON object per text frame, UTF-8. Binary frames are rejected. |
| Health check | HTTP `GET /api/health` → `200 {"ok": true}` |
| Field naming | `camelCase` on the wire. |
| Times | Absolute times (deadlines, timestamps) are **epoch milliseconds** (number), from the server clock. |

Each connection is a separate seat. A player who reconnects opens a new socket and sends
`room:join` with their `roomToken` (see 4.2).

## 2. Envelope

### 2.1 Client → server (request)

```json
{"id": 7, "type": "room:join", "payload": {"code": "ABCD", "profile": {"...": "..."}}}
```

| Field | Type | Rules |
| --- | --- | --- |
| `id` | integer | Chosen by the client and echoed in the ack. Use increasing numbers. |
| `type` | string | One of the request types in section 4. |
| `payload` | object | Required. Use `{}` when the request has no fields. |

### 2.2 Server → client: ack (exactly one per request)

Success:

```json
{"type": "ack", "id": 7, "ok": true, "data": {}}
```

Failure:

```json
{"type": "ack", "id": 7, "ok": false, "error": {"code": "ROOM_NOT_FOUND", "message": "We couldn't find room ABCD."}}
```

`message` is human-readable English and may change; code against `code`.

### 2.3 Server → client: pushes (no `id`)

| `type` | Payload field | When |
| --- | --- | --- |
| `room:state` | `data: RoomPublic` | After every room change, to everyone online in the room. |
| `game:view` | `data: {gameId, view, serverNow}` | After every game change, to each online player separately (personalized). |
| `game:event` | `data: {kind, data}` | Transient moments: reveal, round over, elimination, challenge opened, game over. Same for everyone. |
| `error` | `data: {code, message}` | A problem not tied to a request (see below). |

`serverNow` is the server's epoch-ms clock when the view was sent. Compute countdowns as
`deadline - serverNow`, measured from when the view arrived, so a wrong phone clock doesn't matter.

`error` pushes are sent when:
- a frame has no usable `id` (not JSON, not an object, missing/non-integer `id`, binary frame):
  `{"code": "BAD_MESSAGE", ...}`;
- this socket lost its seat, because the room was closed by cleanup or the same seat was
  reclaimed from another socket with its `roomToken`: `{"code": "NOT_IN_ROOM", ...}`. The socket
  stays open and may create or join a room again.

**Ordering:** pushes caused by a request may arrive **before** its ack (for example the
`room:state` after `room:join`). Treat pushes as the source of truth for state.

Example push:

```json
{"type": "room:state", "data": {"code": "ABCD", "hostId": "p_x1", "status": "lobby", "players": [], "selectedGame": null, "settings": {}, "scoreboard": {}}}
```

## 3. Error codes

| Code | Meaning |
| --- | --- |
| `ROOM_NOT_FOUND` | No room with that code. |
| `ROOM_FULL` | The room already has `MAX_PLAYERS` (10) players. |
| `NAME_TAKEN` | Reserved. Duplicate nicknames are auto-suffixed (`Sam`, `Sam2`, `Sam3`), so this is not normally sent. |
| `NOT_HOST` | Host-only request sent by a non-host. |
| `NOT_YOUR_TURN` | A game action out of turn. |
| `INVALID_ACTION` | Invalid payload, profile, settings, or game move. Also used for an unexpected server error ("Something went wrong."). |
| `GAME_IN_PROGRESS` | Joining a room mid-game without a valid `roomToken` for a seat. |
| `RATE_LIMITED` | More than `ACTION_RATE_LIMIT_PER_SEC` (5) game actions per second on this connection. |
| `NOT_IN_ROOM` | Request needs a room but this connection has no seat (never joined, left, or was detached). |
| `UNKNOWN_EVENT` | `type` is not a known request type. |
| `BAD_MESSAGE` | Frame is not valid JSON, or the envelope is malformed. |

## 4. Requests

### 4.1 `room:create`

Payload: `{ "profile": Profile }`. Creates a room; the sender becomes host.

Ack data:

```json
{"playerId": "p_x1", "roomToken": "Xb9...", "room": {"code": "ABCD", "...": "RoomPublic"}}
```

Store `roomToken` per room code (e.g. localStorage); it reclaims the seat after a disconnect.
`roomToken` is only ever sent to its owner.

A socket holds at most one seat: `room:create`/`room:join` while already seated replies
`INVALID_ACTION` ("Leave your current room first.").

### 4.2 `room:join`

Payload: `{ "code": "ABCD", "profile": Profile, "roomToken"?: string }`

- `code` is case-insensitive (uppercased by the server).
- With a `roomToken` matching a seated player: reclaims that seat (same `playerId`, nickname,
  emoji and color; the sent profile is validated but not applied), marks it online, and allowed in
  any status, including mid-game. If another socket still held the seat, that socket gets an
  `error` push `NOT_IN_ROOM`. A reconnecting player in a running game also receives a `game:view`.
- Without a valid token: takes a new seat. Rejected with `GAME_IN_PROGRESS` while the room is
  `playing`; allowed in `lobby` and `finished`. An unknown or stale token is simply ignored.
- Nickname clashes (case-insensitive) get the lowest free suffix from 2: `Sam`, `Sam2`, `Sam3`.
  The base is shortened if needed to stay within 12 characters (`Alexandrinas` → `Alexandrina2`).

Check order: profile (`INVALID_ACTION`), room exists (`ROOM_NOT_FOUND`), token reclaim,
`GAME_IN_PROGRESS`, `ROOM_FULL`.

Ack data: same shape as `room:create`.

Errors: `ROOM_NOT_FOUND`, `ROOM_FULL`, `GAME_IN_PROGRESS`, `INVALID_ACTION` (bad profile).

### 4.3 `room:peek`

Payload: `{ "code": "ABCD" }`. Works without being in a room. Never fails for a missing room.

Ack data:

```json
{"exists": true, "hostNickname": "Sam", "playerCount": 3, "status": "lobby"}
```

For an unknown or malformed code: `{"exists": false, "hostNickname": null, "playerCount": 0, "status": null}`.
`playerCount` excludes players who left mid-game.

### 4.4 `room:leave`

Payload: `{}`. Leaves the current room. Ack data: `{}`. Errors: `NOT_IN_ROOM`.
The `roomToken` stops working.

- In `lobby`/`finished`: the seat and its scoreboard entries are removed.
- In `playing`: the seat stays in `players` with `online: false` (the game treats the player as
  offline for good) and is removed, with its scoreboard entries, when the game ends.
- If the leaver was host, host passes immediately (see 6.3).
- When the last player leaves, the room is deleted.

### 4.5 `room:selectGame` (host only)

Payload: `{ "gameId": GameId, "settings": object }`. Only in `lobby`. Settings are validated by the
game module and completed with defaults; the stored result appears in `RoomPublic.settings`.
Ack data: `{}`. Errors: `NOT_IN_ROOM`, `NOT_HOST`, `INVALID_ACTION` (unknown game, bad settings,
room `finished`), `GAME_IN_PROGRESS`.

### 4.6 `game:start` (host only)

Payload: `{}`. Only in `lobby`. Requires a selected game and a seated-player count within its
min/max (offline players count and take part). Everyone receives `room:state` (status `playing`)
then their first `game:view`.
Ack data: `{}`. Errors: `NOT_IN_ROOM`, `NOT_HOST`, `INVALID_ACTION` (no game selected, wrong
player count, room `finished`), `GAME_IN_PROGRESS`.

### 4.7 `game:action`

Payload: `{ "type": string, ...actionFields }`. Action types are per game (section 7).

Server checks in this order: in a room (`NOT_IN_ROOM`), room status `playing` (`INVALID_ACTION`),
rate limit (`RATE_LIMITED`), then the game module (`NOT_YOUR_TURN` / `INVALID_ACTION`).
On failure nothing changes. On success every player receives a fresh `game:view`.
Ack data: `{}`.

### 4.8 `game:playAgain` (host only)

Payload: `{}`. Returns a `finished` (or `lobby`) room to `lobby`, keeping the selected game,
settings, scoreboard and wins.
Ack data: `{}`. Errors: `NOT_IN_ROOM`, `NOT_HOST`, `GAME_IN_PROGRESS`.

## 5. Types

```ts
type GameId = 'rps' | 'guess_race' | 'hangman' | 'dots_and_boxes' | 'liars_dice' | 'name_it';

// Sent by the client. Unknown fields (including `stats`) are ignored.
type Profile = {
  id: string;               // browser profile id (e.g. crypto.randomUUID())
  nickname: string;         // trimmed; NICKNAME_MIN..NICKNAME_MAX chars; matches NICKNAME_ALLOWED_PATTERN
  emoji: string;            // one of EMOJI_PRESETS
  color: string;            // one of PLAYER_COLORS
  type: 'guest' | 'registered';
};

type Player = {
  id: string;               // per-room player id
  profileId: string;
  nickname: string;         // may carry a suffix: "Sam2"
  emoji: string;
  color: string;
  online: boolean;
  joinedAt: number;         // epoch ms
};

type RoomStatus = 'lobby' | 'playing' | 'between_rounds' | 'finished';

type RoomPublic = {
  code: string;
  hostId: string;
  status: RoomStatus;
  players: Player[];        // seat (join) order
  selectedGame: GameId | null;
  settings: Record<string, unknown>;
  scoreboard: Record<string, number>;   // playerId -> session points (only players with points recorded)
  wins: Record<string, number>;         // playerId -> games won (placement 1) this session
};

type GameResult = { playerId: string; placement: number; points: number };
```

Constants (`shared/constants.json`) are shared by client and server.

## 6. Room lifecycle

### 6.1 Status

| Status | Meaning | Entered by |
| --- | --- | --- |
| `lobby` | Picking a game. | Room created; `game:playAgain`. |
| `playing` | A game is running. | `game:start`. |
| `finished` | Last game over; results on screen. | The game ends. |
| `between_rounds` | Not used in v1. Rounds are phases inside each game's `game:view`. | — |

### 6.2 Game over

When a game ends the server sends, in order:
1. the final `game:view` to each player;
2. any `game:event`s from the final move;
3. `game:event` `{"kind": "gameOver", "data": {"results": GameResult[]}}`, sorted as the game reports them;
4. `room:state` with status `finished`, updated `scoreboard` (points added) and `wins`
   (+1 for every placement-1 player, so ties share the win). Players who left mid-game are
   removed at this point.

### 6.3 Presence and host

- Socket closes: the seat stays, `online: false`. The game is told and applies its own rules.
- `room:join` with the `roomToken` reclaims the seat (`online: true`).
- Host transfer goes to the **longest-seated online** player:
  - immediately when the host sends `room:leave` (falls back to the longest-seated offline
    player if nobody is online);
  - when the host has been offline for more than `HOST_TRANSFER_MS` (15 s) and someone is online.
  A host who returns within 15 s keeps the role. A former host does not get it back.

### 6.4 Cleanup

Every `ROOM_CLEANUP_INTERVAL_MS` (5 min) the server deletes rooms that have no seated players or
no activity for `ROOM_IDLE_TTL_MS` (2 h). Activity is any successful room or game change.
Connected sockets of a deleted room get an `error` push `NOT_IN_ROOM`.

### 6.5 Rate limit

`game:action` only: at most `ACTION_RATE_LIMIT_PER_SEC` (5) actions per rolling second per
connection, counting every action that reaches the limiter (moves the game then rejects count
too). Excess actions get `RATE_LIMITED` and change nothing.

## 7. Games **(B2–B7)**

Each game's settings, actions, view and events are documented here as it is built.
`game:start` may also fail with `INVALID_ACTION` when a game rejects the player count or
settings combination (for example an RPS duel with 3 players).

| gameId | Phase |
| --- | --- |
| `rps` | B2 |
| `guess_race` | B3 |
| `hangman` | B4 |
| `dots_and_boxes` | B5 |
| `liars_dice` | B6 |
| `name_it` | B7 |

### 7.1 `rps`: Rock-Paper-Scissors

**Players:** 2–10. **Settings** (defaults shown):

```json
{"bestOf": 3, "mode": "duel"}
```

| Setting | Values | Notes |
| --- | --- | --- |
| `bestOf` | `3` \| `5` | First to `bestOf // 2 + 1` round wins takes the match. |
| `mode` | `"duel"` \| `"bracket"` | 2 players always play a duel. A duel with 3+ players is rejected at `game:start`. |

**Action:** `{"type": "pick", "choice": "rock" | "paper" | "scissors"}`

| Error | When |
| --- | --- |
| `INVALID_ACTION` | Unknown `type`, bad `choice`, or you already picked this round. |
| `NOT_YOUR_TURN` | You have no live match (bye, eliminated, match over) or your match is in its reveal pause. |

**Rules**
- Matches in a bracket round run at the same time, each with its own timers. Players are paired
  at random each bracket round. With an odd count, one random player gets a bye and advances.
- Each round has `RPS_PICK_TIMEOUT_MS` (10 s). The round is revealed as soon as both have picked,
  or at the deadline. Someone who did not pick loses the round. If neither picked, or both picked
  the same, it's a tie: no point, and the round is replayed.
- After each reveal there is a `RPS_REVEAL_MS` (3 s) pause. Then the match continues with a new
  round, or ends if someone reached the majority.
- When every match in a bracket round is over, the next bracket round starts at once.
- **Offline:** a player offline for `OFFLINE_FORFEIT_MS` (30 s) forfeits their match. If both
  players have been offline that long, the one who went offline **last** wins.

**View** (`game:view` → `view`):

```ts
type RpsView = {
  phase: 'picking' | 'reveal' | 'matchOver' | 'done';
  // picking/reveal: your match's phase. matchOver: you have no live match (won and waiting,
  // bye, or eliminated and spectating). done: the game is over.
  mode: 'duel' | 'bracket';
  bestOf: 3 | 5;
  bracketRound: number;        // 1-based
  myMatch: number | null;      // index into matches, null if you are not in this bracket round
  myPick: Choice | null;       // your own pick this round (never anyone else's)
  matches: MatchPublic[];      // every match of the current bracket round
  alive: string[];             // player ids still in the competition
  eliminated: string[];
  champion: string | null;
};
type Choice = 'rock' | 'paper' | 'scissors';
type MatchPublic = {
  a: string;
  b: string | null;            // null = bye
  phase: 'picking' | 'reveal' | 'over';
  round: number;               // round within the match, 1-based (ties count)
  scores: Record<string, number>;
  hasPicked: Record<string, boolean>;   // current round only; never the pick itself
  deadline: number | null;     // epoch ms: pick deadline (picking) or end of reveal pause (reveal)
  winner: string | null;       // set once the match is decided
  lastReveal: { round: number; picks: Record<string, Choice | null>; roundWinner: string | null } | null;
};
```

**Events** (`game:event` → `{kind, data}`):

| kind | data |
| --- | --- |
| `reveal` | `{matchIndex, round, picks: {playerId: Choice \| null}, roundWinner: string \| null, scores}` |
| `matchOver` | `{matchIndex, winnerId, loserId: string \| null, reason: 'score' \| 'forfeit' \| 'bye'}` |
| `bracketRound` | `{bracketRound, pairs: [a, b \| null][]}`, sent when bracket round 2+ starts. Round 1 pairs (and its bye) are in the first `game:view`; no events are sent at game start. |
| `gameOver` | see 6.2 |

**Results:**

| Who | Placement | Points |
| --- | --- | --- |
| Champion | 1 | 3 |
| Runner-up (lost the final) | 2 | 2 |
| Lost in the round before the final | 3 (shared) | 1 |
| Lost earlier | Shared by round lost; later rounds rank higher | 0 |

In a duel the loser is runner-up (2 points).

### 7.2 `guess_race`: Word Scramble and Emoji Guess

**Players:** 2–10. **Settings** (defaults shown):

```json
{"content": "mixed", "rounds": 10, "difficulty": "mixed"}
```

| Setting | Values | Notes |
| --- | --- | --- |
| `content` | `"scramble"` \| `"emoji"` \| `"mixed"` | `mixed` picks scramble or emoji at random for each round. |
| `rounds` | `5` \| `10` \| `15` | |
| `difficulty` | `"easy"` \| `"medium"` \| `"hard"` \| `"mixed"` | Scramble words only (easy 4–5 letters, medium 6–7, hard 8–9). |

**Action:** `{"type": "guess", "text": string}`. `text` is 1–`GUESS_TEXT_MAX` (40) characters
and not blank. Wrong guesses are allowed without limit, apart from the rate limit, and are acked `ok: true`.

| Error | When |
| --- | --- |
| `INVALID_ACTION` | Unknown `type`, bad `text`, or the round is no longer accepting guesses. |

**Rules**
- Content never repeats within a game. Everyone sees the same prompt.
- A guess is correct if `normalize(text)` equals the normalized answer or one of its
  alternatives. normalize: lowercase, trim, drop a leading "the ", then remove all punctuation and whitespace.
- The first correct guess wins the round and scores
  `max(20, 100 - 2 * floor(secondsElapsed))`.
- Hint 1 at `GUESS_HINT1_MS` (10 s): the category (emoji) or the letter count (scramble).
  Hint 2 at `GUESS_HINT2_MS` (20 s): the first letter of the answer, ignoring a leading "The".
- The round ends at the first correct guess or at `GUESS_ROUND_MS` (30 s) with no winner. The
  answer is then shown for `GUESS_REVEAL_MS` (3 s), and the next round starts.

**View:**

```ts
type GuessRaceView = {
  phase: 'guessing' | 'roundOver' | 'done';
  round: number;                 // 1-based
  total: number;                 // number of rounds
  kind: 'scramble' | 'emoji';
  prompt: string;                // scramble: UPPERCASE scrambled letters; emoji: the emoji string
  hints: Hint[];                 // in order; all hints are included once the round is over
  roundStartedAt: number;        // epoch ms
  roundEndsAt: number;           // epoch ms: when guessing closes
  revealEndsAt: number | null;   // epoch ms: when the next round starts (roundOver only)
  scores: Record<string, number>;
  roundWinner: string | null;
  roundPoints: number;           // points the round winner earned (0 if none)
  answer: string | null;         // null while guessing; set in roundOver/done
  myLastGuess: { text: string; correct: boolean } | null;   // your own last guess this round
};
type Hint =
  | { type: 'length'; value: number }        // scramble, hint 1
  | { type: 'category'; value: string }      // emoji, hint 1
  | { type: 'firstLetter'; value: string };  // hint 2, one uppercase character
```

**Events:**

| kind | data |
| --- | --- |
| `roundOver` | `{round, answer, winnerId: string \| null, points}` |
| `gameOver` | see 6.2 |

**Results:** placement by total score (ties share). Each player's `points` is their total score,
which is added directly to the session scoreboard.
