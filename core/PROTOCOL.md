# Boredom WebSocket Protocol

> **Status: rooms and all six games complete, with fair scoring (phases R1–R3, S1–S2).** The
> envelope, event names, error codes and room types are fixed. This file is kept in sync
> with the code; if they ever disagree, report it.
>
> **Changes approved after B0:** `RoomPublic.wins` added; `game:view` carries `serverNow`;
> a game's end is announced with `game:event` kind `gameOver`; mid-game `room:leave` keeps the
> seat (offline) until the game ends.
>
> **Contract change (avatars):** the profile `emoji` is gone. Every seat now has a server-assigned
> DiceBear `avatar: {style, seed}` (see 5.1); `EMOJI_PRESETS` was removed from the constants.
>
> **Contract change (fair scoring, S1–S2):** games report a placement and a raw display `score`;
> session `points` are computed centrally from placements (6.2). `GameResult` gained `score`,
> scoreboard values can have 2 decimals, and the per-game rules changed (section 7).
>
> **Contract change (accounts, A1–A4):** optional permanent accounts over HTTP (section 8).
> `room:create` / `room:join` accept an optional `authToken`; a registered seat uses the saved
> profile and avatar, and an invalid token falls back to guest with `authStatus: "invalid"` in
> the ack. `Player.profileId` was **removed** from `room:state` (it leaked every player's
> persistent browser id); `Player.type` (`"guest"` | `"registered"`) was added.
>
> **Additions (ready check and reactions):** additive only; nothing was renamed or removed.
> New requests `room:ready` (4.9) and `room:react` (4.10); new push `room:reaction`;
> `Player.ready` and `RoomPublic.readyCheck` in `room:state`; `room:event` kind `ready_reset`
> (6.6). Older clients can ignore all of it.
>
> **Additions (profile page):** additive only. Every account has a public `tag` (8.6);
> `GET /api/auth/me` gains top-level `tag` and ISO-8601 `createdAt`; new
> `GET /api/me/stats` and `GET /api/me/recent-players` (8.3). The tag is never sent over the
> WebSocket.
>
> **Additions (guest free games):** guests get `GUEST_FREE_GAMES` (7) game starts per
> `GUEST_WINDOW_MS` (2 h), section 11. New request and push `guest:quota`, error code
> `GUEST_LIMIT` (with `error.data`), `Player.locked`; `game:start` leaves out locked guests.
>
> **Additions (guest signup in a room):** `room:join` with a guest seat's `roomToken` and a valid
> `authToken` turns that seat into the account's seat, outside a running game (4.2).
>
> **Additions (friends, presence, invites):** additive only. HTTP endpoints for friends, blocks,
> reports and the presence setting (8.7); `RecentPlayer.relationship`. Over the WebSocket: new
> requests `auth:hello`, `invite:send`, `invite:accept`, `invite:decline`,
> `friends:requestByPlayer`, `player:block`, `player:report`; new pushes `friends:snapshot`,
> `friends:presence`, `friends:request`, `friends:accepted`, `friends:removed`,
> `invite:received`, `invite:expired`, `invite:cleared`; new error codes (3). Section 9. Tags
> are now sent over the WebSocket, but only to the account's friends (and with a friend
> request or invite to its recipient). `room:state` is unchanged.

## 1. Transport

| Item | Value |
| --- | --- |
| WebSocket URL | `ws(s)://<server-host>/ws/` (single endpoint) |
| Origin check | The browser `Origin` host must be in `DJANGO_ALLOWED_HOSTS`, otherwise the socket is closed. |
| Encoding | One JSON object per text frame, UTF-8. Binary frames are rejected. |
| Health check | HTTP `GET /api/health` → `200 {"ok": true}` |
| Accounts | HTTP JSON API under `/api/auth/` (section 8). Optional; guests need none of it. |
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

`message` is human-readable English and may change; code against `code`. Some errors also
carry `error.data` (only `GUEST_LIMIT` so far, section 11).

### 2.3 Server → client: pushes (no `id`)

| `type` | Payload field | When |
| --- | --- | --- |
| `room:state` | `data: RoomPublic` | After every room change, to everyone online in the room. |
| `game:view` | `data: {gameId, view, serverNow}` | After every game change, to each online player separately (personalized). |
| `game:event` | `data: {kind, data}` | Transient moments: reveal, round over, elimination, challenge opened, game over. Same for everyone. |
| `room:event` | `data: {kind, playerId, nickname, data?}` | Transient room moments (6.6). Never replayed on reconnect. |
| `room:reaction` | `data: {id, playerId, nickname, emoji}` | Someone sent an emoji reaction (4.10). To everyone online in the room, the sender included. Never stored or replayed. |
| `error` | `data: {code, message}` | A problem not tied to a request (see below). |
| `friends:*`, `invite:*` | see 9 | Friends' presence, friend requests and room invites, to signed-in accounts only (9.3). |

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
{"type": "room:state", "data": {"code": "ABCD", "hostId": "p_x1", "status": "lobby", "players": [{"id": "p_x1", "type": "guest", "nickname": "Sam", "color": "#E74C3C", "avatar": {"style": "voxel-art", "seed": "9c41e07b"}, "online": true, "joinedAt": 1792324569015.47}], "selectedGame": null, "settings": {}, "scoreboard": {}, "wins": {}}}
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
| `RATE_LIMITED` | More than `ACTION_RATE_LIMIT_PER_SEC` (5) game actions per second on this connection, or a `room:react` within `REACTION_COOLDOWN_MS` of the player's previous one. |
| `NOT_IN_ROOM` | Request needs a room but this connection has no seat (never joined, left, or was detached). |
| `UNKNOWN_EVENT` | `type` is not a known request type. |
| `BAD_MESSAGE` | Frame is not valid JSON, or the envelope is malformed. |
| `UNAUTHORIZED` | `auth:hello` with a missing, invalid or expired token, or a disabled or deleted account (9.1). |
| `NOT_FRIENDS` | `invite:send` to someone who is not your friend (or an unknown tag). |
| `GUEST_LIMIT` | A guest out of free games (11): `room:create` / `room:join` for a new seat, with `data: {lockedUntil}`; `game:start` when too few players are left, with `data: {nicknames}`. |
| `TARGET_UNAVAILABLE` | `invite:send` to a friend who is not exactly `online` (offline, appearing offline, busy, in a room), blocked, or disabled. Always the same message. |
| `INVITE_EXPIRED` | `invite:accept` after the invite ran out, or its room started a game, closed, or the sender left. |
| `INVITE_INVALID` | `invite:accept` for an invite that is not yours, was already used, never existed (or was lost in a server restart), or after a block. |
| `SELF`, `ALREADY_FRIENDS`, `ALREADY_REQUESTED`, `LIMIT_REACHED`, `INVALID_INPUT` | From the by-player actions (9.5), with the meaning they have in the HTTP API (8.7). `RATE_LIMITED` is also used for invite and friend-request limits. |

## 4. Requests

### 4.1 `room:create`

Payload: `{ "profile": Profile, "authToken"?: string }`. Creates a room; the sender becomes host.

Ack data:

```json
{"playerId": "p_x1", "roomToken": "Xb9...", "room": {"code": "ABCD", "...": "RoomPublic"}}
```

**`authToken`** (also on `room:join`): the access token from the account API (section 8).

| `authToken` | Seat | Ack data |
| --- | --- | --- |
| absent or `null` | Guest from `profile` (unchanged behaviour). | as above |
| valid | `type: "registered"`. The account's saved nickname, color and avatar are used; the client's `profile` fields are **ignored** and `profile` may be omitted. | as above |
| invalid, expired, or for a disabled/deleted account | Guest from `profile` (which must then be valid). | as above plus `"authStatus": "invalid"`: tell the user to log in again. |

Example ack after a stale token:

```json
{"type": "ack", "id": 1, "ok": true, "data": {"playerId": "p_x1", "roomToken": "Xb9...", "room": {"...": "RoomPublic"}, "authStatus": "invalid"}}
```

Keep sending `profile` with an `authToken`, so an expired token still gets a guest seat.

Store `roomToken` per room code (e.g. localStorage); it reclaims the seat after a disconnect.
`roomToken` is only ever sent to its owner.

A socket holds at most one seat: `room:create`/`room:join` while already seated replies
`INVALID_ACTION` ("Leave your current room first.").

### 4.2 `room:join`

Payload: `{ "code": "ABCD", "profile": Profile, "roomToken"?: string, "authToken"?: string }`
(`authToken`: see 4.1.)

- `code` is case-insensitive (uppercased by the server).
- With a `roomToken` matching a seated player: reclaims that seat (same `playerId`, nickname,
  color and **avatar**; the sent profile is validated but not applied), marks it online, and allowed in
  any status, including mid-game. If another socket still held the seat, that socket gets an
  `error` push `NOT_IN_ROOM`. A reconnecting player in a running game also receives a `game:view`.
- With a valid `authToken` for an account that already holds a seat here: reclaims that seat
  exactly like a `roomToken` (same `playerId` and `roomToken` in the ack, older socket detached).
  One account never holds two seats in a room.
- With a `roomToken` for a **guest** seat plus a valid `authToken` (the guest just signed up or
  logged in): the seat becomes the account's (`type` turns `"registered"`; same `playerId`,
  nickname, color, avatar and score), unless the room is `playing` or the account already holds
  another seat here, in which case it is reclaimed unchanged as a guest seat.
- Without a valid token: takes a new seat with a **newly assigned avatar** (5.1). Rejected with
  `GAME_IN_PROGRESS` while the room is `playing`; allowed in `lobby` and `finished`. An unknown or
  stale token is simply ignored.
- Nickname clashes (case-insensitive) get the lowest free suffix from 2: `Sam`, `Sam2`, `Sam3`.
  The base is shortened if needed to stay within 12 characters (`Alexandrinas` → `Alexandrina2`).

Check order: profile or account (`INVALID_ACTION`), room exists (`ROOM_NOT_FOUND`), seat reclaim
(`roomToken`, then account), `GAME_IN_PROGRESS`, `ROOM_FULL`.

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

Picking a different game, or changing at least one stored setting value, clears every ready flag
(4.9) and sends `ready_reset` to the players whose flag was set. Sending the same game with
settings that validate to the same values changes nothing.

### 4.6 `game:start` (host only)

Payload: `{}`. Only in `lobby`. Requires a selected game and a seated-player count within its
min/max (offline players count and take part). Everyone receives `room:state` (status `playing`)
then their first `game:view`.
Ack data: `{}`. Errors: `NOT_IN_ROOM`, `NOT_HOST`, `INVALID_ACTION` (no game selected, wrong
player count, room `finished`), `GAME_IN_PROGRESS`, `GUEST_LIMIT` (11).
Locked guests (11) sit the game out (`inGame: false` from the start) and are not counted in the
player count.

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

### 4.9 `room:ready` (non-host players)

Payload: `{ "ready": boolean }`. Marks the sender ready (or not) for the selected game. Allowed
only while the room is `lobby`, a game is selected, and the sender is **not** the host.
On a change everyone receives `room:state`. Ack data: `{}`.
Errors: `NOT_IN_ROOM`, `INVALID_ACTION` (not a boolean, sender is host, no game selected,
room not in `lobby`).

The ready check is advisory: `game:start` is **never** blocked by it.

| Rule | Detail |
| --- | --- |
| `Player.ready` | The seat's flag. Always `false` for the host. |
| `RoomPublic.readyCheck` | `{count, total}`: `total` = online non-host seated players, `count` = those of them who are ready. Offline players are left out of both numbers but keep their flag. `null` while no game is selected. |
| Reset to `false` for everyone | The host selects a different game or changes a setting value (sends `ready_reset`, 6.6); a game starts; the room returns to `lobby` (`game:playAgain`, `game:end`, or a game abandoned by forfeits). |
| Seats | A new seat starts `false`. A seat reclaimed by `roomToken` or account keeps its flag. A player who becomes host loses their flag. |

### 4.10 `room:react`

Payload: `{ "emoji": string }`. `emoji` must be exactly one of `REACTION_EMOJIS`
(`👏 😂 😮 🔥 😭 🤔 🎉 ❤️`; `❤️` includes U+FE0F). Allowed in every room status, including for a
player who forfeited the running game. A player who left the room cannot react.

Each player may react once per `REACTION_COOLDOWN_MS` (700 ms); a faster request gets
`RATE_LIMITED` and is not delivered. On success everyone online in the room, the sender
included, receives:

```json
{"type": "room:reaction", "data": {"id": "r_3f9a0c1b2d4e", "playerId": "p_x1", "nickname": "Sam", "emoji": "🔥"}}
```

`id` is unique per reaction (for client-side keys). Reactions are not part of room state: they
are never stored, never replayed on reconnect, never recorded in activity or analytics, and do
not count as room activity for cleanup (6.4).
Ack data: `{}`. Errors: `NOT_IN_ROOM`, `INVALID_ACTION` (unknown emoji), `RATE_LIMITED`.

## 5. Types

```ts
type GameId = 'rps' | 'guess_race' | 'hangman' | 'dots_and_boxes' | 'liars_dice' | 'name_it';

// Sent by the client. Unknown fields (including `type`, `stats` and an old `emoji`) are ignored:
// the server decides the seat type from `authToken` (4.1). Ignored entirely with a valid authToken.
type Profile = {
  id: string;               // browser profile id (e.g. crypto.randomUUID()); never sent to other players
  nickname: string;         // trimmed; NICKNAME_MIN..NICKNAME_MAX chars; matches NICKNAME_ALLOWED_PATTERN
  color: string;            // one of PLAYER_COLORS
  avatar?: Avatar;          // optional; validated if present, then IGNORED for guests (see 5.1)
};

type Avatar = {
  style: string;            // one of AVATAR_STYLES
  seed: string;             // matches AVATAR_SEED_PATTERN
};

type Player = {
  id: string;               // per-room player id
  type: 'guest' | 'registered';  // for a badge; no username or account id is ever exposed
  nickname: string;         // may carry a suffix: "Sam2"
  color: string;
  avatar: Avatar;           // assigned by the server when the seat is created
  online: boolean;
  joinedAt: number;         // epoch ms
  ready: boolean;           // lobby ready check (4.9); always false for the host
  locked: boolean;          // a guest out of free games (11); always false for registered seats
};

type RoomStatus = 'lobby' | 'playing' | 'between_rounds' | 'finished';

type RoomPublic = {
  code: string;
  hostId: string;
  status: RoomStatus;
  players: Player[];        // seat (join) order
  selectedGame: GameId | null;
  settings: Record<string, unknown>;
  scoreboard: Record<string, number>;   // playerId -> session points, up to 2 decimals (only players with points recorded)
  wins: Record<string, number>;         // playerId -> games won (placement 1) this session
  readyCheck: { count: number; total: number } | null;  // 4.9; null while no game is selected
};

type GameResult = {
  playerId: string;
  placement: number;   // 1 is best; tied players share a placement (1, 2, 2, 4)
  score: number;       // raw in-game score, for display only (meaning per game, section 7)
  points: number;      // session points this game added to the scoreboard (6.2)
};
```

Constants (`shared/constants.json`) are shared by client and server.

### 5.1 Avatars

Each seat gets a DiceBear avatar, described only by `{style, seed}`. The server never stores or
sends image URLs. The client builds the image from `AVATAR_API_VERSION`, `style` and `seed`,
for example `https://api.dicebear.com/{AVATAR_API_VERSION}/{style}/svg?seed={seed}`.

| Rule | Detail |
| --- | --- |
| New guest seat (`room:create`, or `room:join` without a valid token) | The server picks a random style from `AVATAR_STYLES` and a random seed (8 hex characters). Any `avatar` the guest sent is ignored. |
| Reclaimed seat (valid `roomToken`) | Keeps its existing avatar unchanged. |
| Registered seat (valid `authToken`) | The avatar saved with the account, in every room and game, forever (8.3). |
| Uniqueness | No two guest seats in a room share the same `{style, seed}`. A registered seat keeps its saved avatar even if a guest seat happens to match it. |
| Validation | A `profile.avatar` that is present must be an object with `style` in `AVATAR_STYLES` and `seed` matching `AVATAR_SEED_PATTERN`; otherwise the request fails with `INVALID_ACTION`. |
| Privacy | Seeds are random. They are never derived from the nickname, profile id or anything identifying. |

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

Afterwards, in the background, every registered player's account stats get `played + 1`, and
`wins + 1` for placement 1 (8.4). A failed stats write is logged and never affects the game.

**Session points** are the same for every game and depend only on placement. With `n`
players in the game, position `p` is worth `SESSION_POINTS_MAX × (n − p) / (n − 1)`
(`SESSION_POINTS_MAX` = 100): 1st gets 100, last gets 0. Tied players share the **average** of
the positions they occupy (two tied for 1st of 4 each get (100 + 66.67) / 2 = 83.33). A
one-player game gives 100. Points are rounded to 2 decimals. Raw game scores never reach the
scoreboard, so no game is worth more than another.

| Players | 1st | 2nd | 3rd | 4th |
| --- | --- | --- | --- | --- |
| 2 | 100 | 0 | | |
| 3 | 100 | 50 | 0 | |
| 4 | 100 | 66.67 | 33.33 | 0 |

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

`room:react` has its own per-player cooldown instead (4.10).

### 6.6 Room events

`room:event` pushes announce transient room moments. `playerId` and `nickname` name the player
the event is about (or who caused it); `data` is present only for kinds that need it. They are
sent to everyone online in the room unless noted, and are never replayed on reconnect.

| `kind` | About | `data` |
| --- | --- | --- |
| `player_left` | The player who sent `room:leave`. | |
| `player_offline` | A player still offline `OFFLINE_NOTICE_DELAY_MS` after disconnecting. | |
| `player_online` | That player came back. | |
| `host_changed` | The new host. | `{previousHostId}` |
| `player_quit` | The player who sent `game:quit`. | |
| `game_ended_by_host` | The host who sent `game:end`. | |
| `ready_reset` | The host whose change cleared the flags. Sent **only** to players whose ready flag was `true` and was cleared by that change. | `{reason: "game_changed" \| "settings_changed"}` |

## 7. Games **(B2–B7)**

Each game's settings, actions, view and events are documented here as it is built.
`game:start` may also fail with `INVALID_ACTION` when a game rejects the player count or
settings combination (for example an RPS duel with 3 players).

| gameId | Phase |
| --- | --- |
| `rps` | B2 |
| `guess_race` | B3 |
| `hangman` | B4 |
| `dots_and_boxes` | B5 (R1) |
| `liars_dice` | B6 (R2) |
| `name_it` | B7 (R3) |

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
  The bye goes only to a player who has not had one yet, while such a player is still in.
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

**Results:** placement by the bracket round a player lost in; `score` is matches won (byes
are not wins).

| Who | Placement |
| --- | --- |
| Champion | 1 |
| Runner-up (lost the final) | 2 |
| Lost in the round before the final | 3 (shared) |
| Lost earlier | Shared by round lost; later rounds rank higher |

In a duel the loser is runner-up.

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
| `INVALID_ACTION` | Unknown `type`, bad `text`, you already solved this round, or the round is no longer accepting guesses. |

**Rules**
- Content never repeats within a game, nor across games in the same room: the server remembers
  what a room has played and only reuses a pool (a word band, or the emoji puzzles) once all
  of it has been played. Everyone sees the same prompt.
- A guess is correct if `normalize(text)` equals the normalized answer or one of its
  alternatives. normalize: lowercase, trim, drop a leading "the ", then remove all punctuation and whitespace.
  For a scramble, every listed word made of the same letters is correct (LISTEN, SILENT,
  ENLIST); `answer` shows the one that was picked. The scrambled letters are never a listed word.
- **Everyone can score.** Each player who solves the round earns points by finishing order
  (the order the server received the correct guesses, so there are no exact ties): rank `k`
  earns `max(GUESS_RANK_POINTS_FLOOR, GUESS_RANK_POINTS_FIRST − GUESS_RANK_POINTS_STEP × (k − 1))`,
  that is 100, 80, 60, 40, then 20 for everyone after. Players who don't solve it earn 0.
  Once you solve it you can't guess again that round.
- Hint 1 at `GUESS_HINT1_MS` (10 s): the category (emoji) or the letter count (scramble).
  Hint 2 at `GUESS_HINT2_MS` (20 s): the first letter of the answer, ignoring a leading "The".
- The first correct guess of a round leaves everyone else `GUESS_SOLVED_WINDOW_MS` (10 s) to
  solve it too, never past the usual end; the view's `roundEndsAt` moves to that earlier time.
  The round ends then, when every **online** player has solved it (going offline can end it
  too), or at `GUESS_ROUND_MS` (30 s), whichever comes first. The answer is then shown for
  `GUESS_REVEAL_MS` (3 s), and the next round starts.

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
  solvers: Solver[];             // this round, in finishing order (public; never the answer)
  iSolved: boolean;              // you solved this round
  answer: string | null;         // null while guessing; set in roundOver/done
  myLastGuess: { text: string; correct: boolean } | null;   // your own last guess this round
};
type Solver = { playerId: string; rank: number; points: number };
type Hint =
  | { type: 'length'; value: number }        // scramble, hint 1
  | { type: 'category'; value: string }      // emoji, hint 1
  | { type: 'firstLetter'; value: string };  // hint 2, one uppercase character
```

**Events:**

| kind | data |
| --- | --- |
| `roundOver` | `{round, answer, solvers: Solver[]}` |
| `gameOver` | see 6.2 |

**Results:** placement by total score (ties share). `score` is the total score.

### 7.3 `hangman`: Hangman Duel

**Players:** 2–10. **Settings** (defaults shown):

```json
{"mode": "group"}
```

| Setting | Values | Notes |
| --- | --- | --- |
| `mode` | `"group"` \| `"duel"` | `duel` needs exactly 2 players (rejected at `game:start` otherwise). With 2 players the two modes play identically. |

There is one round per player. Every player sets a word exactly once, in join order, and
guesses every other player's word.

**Actions:**

| Action | Who | Rules |
| --- | --- | --- |
| `{"type": "setWord", "word": string, "hint"?: string}` | the setter, while `setting` | `word` is `HANGMAN_WORD_MIN`–`HANGMAN_WORD_MAX` (5–10) letters A–Z, stored uppercase. `hint` is optional, trimmed, at most `HANGMAN_HINT_MAX` (30) characters from `NICKNAME_ALLOWED_PATTERN`. A blank hint means none. |
| `{"type": "guessLetter", "letter": string}` | any guesser, while `guessing` | One letter A–Z, case-insensitive, not already guessed by anyone. |
| `{"type": "flagWord"}` | any guesser, while `roundOver` | Claims the word is not a real word. Within `HANGMAN_FLAG_WINDOW_MS` (5 s) of the round ending, once per round, only after a played word (not a skipped round), and only with 3+ players. |
| `{"type": "voteWord", "valid": boolean}` | each voter once, while `flagVote` | Voters are all guessers (never the setter). The flagger has already voted Invalid. |

| Error | When |
| --- | --- |
| `NOT_YOUR_TURN` | `setWord` from a non-setter or outside `setting`; `guessLetter` outside `guessing`. |
| `INVALID_ACTION` | Bad word, hint or letter; letter already guessed; the setter tries to guess; flag not allowed (setter, window over, already flagged, skipped round, fewer than 3 players); vote by a non-voter, twice, or not a boolean; unknown `type`. |

**Rules**
- All guessers share one pool of `HANGMAN_MAX_WRONG` (6) wrong letters and may guess at any
  time. The first valid guess of a letter counts; the same letter again is rejected.
- Guessers win when every letter is revealed. The setter wins when the 6th wrong letter is guessed.
- **Scoring:** every round is a fixed pot of `HANGMAN_POT` (12) points, whatever the word's
  length. Points are given when the round ends:

  | Outcome | Setter | Guessers (split equally among all guessers) |
  | --- | --- | --- |
  | Solved with `w` wrong letters | `HANGMAN_WRONG_COST × w` (2w) | `POT − 2w` |
  | Figure completes, or every guesser offline 30 s | `POT` | 0 |
  | Setter never sets a word (skipped) | 0 | `POT` |
  | Flag upheld (see below) | 0 | `POT` |

  Setter plus guessers always add up to exactly `POT`. Scores can have fractions in group mode
  (shown rounded to 2 decimals).
- **Not-a-real-word flag:** after a played round, any guesser may send `flagWord` within 5 s.
  The game moves to `flagVote` for `HANGMAN_VOTE_MS` (8 s). Votes are secret until the vote
  closes. It closes early once every voter has voted.
  - The flag is **upheld** only if more than half of **all** voters voted Invalid. The
    flagger's own vote counts as Invalid. Ties, missing votes and absent voters keep the word valid.
  - If upheld, the round's award is replaced: the setter gets 0 and the guessers share the full pot.
  - Flagging is disabled with fewer than 3 players, because there would be no neutral voter.
  - After the vote, the next round starts at once.
- **Timers:**
  - The setter has `HANGMAN_SET_WORD_MS` (60 s) to set a word. If they don't, the round is
    skipped (`result: "skipped"`) and the guessers share the pot.
  - Guessing has no timer. If **every** guesser has been offline for `OFFLINE_FORFEIT_MS`
    (30 s), the setter wins the round.
  - After a round, the word is shown for `HANGMAN_REVEAL_MS` (3 s), or for the 5 s flag
    window when flagging is possible, whichever is longer. Then the next round starts.

**View:**

```ts
type HangmanView = {
  phase: 'setting' | 'guessing' | 'roundOver' | 'flagVote' | 'done';
  round: number;               // 1-based
  total: number;               // = number of players
  setterId: string;
  isSetter: boolean;
  mask: (string | null)[];     // one cell per letter; null = hidden. Empty while setting.
  word: string | null;         // setter only during the round; everyone in roundOver/flagVote/done
  hint: string | null;
  guessed: string[];           // every letter guessed this round, in order (uppercase)
  wrong: string[];             // wrong letters, in order
  wrongCount: number;
  maxWrong: number;            // 6
  deadline: number | null;     // epoch ms: setter deadline, round-over end, or vote close
  result: 'guessers' | 'setter' | 'skipped' | null;   // set in roundOver/flagVote/done
  award: Record<string, number>;   // this round's points per player (after the round ends)
  scores: Record<string, number>;  // totals, 2 decimals
  pot: number;                 // HANGMAN_POT
  wrongCost: number;           // HANGMAN_WRONG_COST
  flagUntil: number | null;    // epoch ms: flag window end (roundOver only)
  canFlag: boolean;            // you are a guesser and a flag is possible this round (check flagUntil)
  flag: {                      // only during flagVote
    flaggerId: string;
    deadline: number;
    voterIds: string[];
    votedCount: number;        // how many voted; never who voted what
    canVote: boolean;
    hasVoted: boolean;         // your own status only
  } | null;
};
```

**Events:**

| kind | data |
| --- | --- |
| `roundOver` | `{round, setterId, word: string \| null, result: 'guessers' \| 'setter' \| 'skipped', award: Record<string, number>}` |
| `wordFlagged` | `{round, flaggerId}` |
| `flagResult` | `{round, setterId, word, flaggerId, votes: Record<playerId, boolean>, validVotes, invalidVotes, upheld: boolean, award}` (`award` is the round's final award) |
| `gameOver` | see 6.2 |

**Results:** placement by total score across the whole game (ties share). `score` is the total.

### 7.4 `dots_and_boxes`: Dots and Boxes

**Players:** 2–4. **Settings** (defaults shown):

```json
{"size": 5}
```

| Setting | Values | Notes |
| --- | --- | --- |
| `size` | integer `4`–`7` | Boxes per side. The board has `size + 1` dots per side. |

**Line ids:** `h:r:c` is the horizontal line from dot (r, c) to dot (r, c+1), with r `0..size`
and c `0..size-1`. `v:r:c` is the vertical line from dot (r, c) to dot (r+1, c), with r
`0..size-1` and c `0..size`. Box (r, c) is bounded by `h:r:c`, `h:{r+1}:c`, `v:r:c` and
`v:r:{c+1}`. There are `2 × size × (size + 1)` lines.

**Action:** `{"type": "drawLine", "id": string}`

| Error | When |
| --- | --- |
| `NOT_YOUR_TURN` | It is another player's turn. |
| `INVALID_ACTION` | Unknown or off-board line id; line already drawn; game over; unknown `type`. |

**Rules**
- The turn order is shuffled at random when the game starts (`order` in the view).
- Drawing the fourth side of a box claims it for the drawer. One line can close two boxes.
  Closing at least one box keeps the turn; otherwise the turn passes.
- The game ends when every box is claimed (that is, when every line is drawn).
- **Timers:** each turn lasts `DOTS_TURN_MS` (45 s); the timer restarts after every line,
  including extra turns. When it runs out, the server draws a line for the current player.
  - A player who has been offline for `OFFLINE_FORFEIT_MS` (30 s) is auto-played as soon as
    their turn comes (or at the 30 s mark if it is already their turn), until they return.
  - Auto-moves pick a random free line that does not give any box its third side. If every
    free line does, any free line is picked.

**View** (everything is public; every player gets the same view apart from `isYourTurn`):

```ts
type DotsView = {
  phase: 'playing' | 'done';
  size: number;
  order: string[];                      // player ids in turn order
  currentPlayerId: string | null;       // null when done
  isYourTurn: boolean;
  lines: Record<string, string>;        // drawn line id -> drawer's player id
  boxes: (string | null)[][];           // [row][col] -> owner's player id or null
  scores: Record<string, number>;       // boxes owned
  lastMove: {
    lineId: string;
    playerId: string;                   // who the line was drawn for
    boxes: [number, number][];          // boxes it closed, as [row, col]
    auto: 'timeout' | 'offline' | null; // set when the server drew it
  } | null;
  turnDeadline: number | null;          // epoch ms; null when done
};
```

**Events:** only `gameOver` (see 6.2).

**Results:** placement by boxes owned (ties share; a tie for most boxes is a shared win).
`score` is the box count.

### 7.5 `liars_dice`: Liar's Dice

**Players:** 2–6. **Settings** (defaults shown):

```json
{"startingDice": 5, "wildOnes": false, "spotOn": false}
```

| Setting | Values | Notes |
| --- | --- | --- |
| `startingDice` | integer `3`–`6` | Dice per player at the start. Also the most a player can hold. |
| `wildOnes` | boolean | Ones count as any face, except when the bid is on ones. |
| `spotOn` | boolean | Enables the `callSpotOn` action. |

**Actions** (only the current player, only while `bidding`):

| Action | Rules |
| --- | --- |
| `{"type": "bid", "quantity": int, "face": int}` | `face` 1–6; `quantity` from 1 to the total dice in play. Must beat the current bid: a higher quantity, or the same quantity and a higher face. |
| `{"type": "callLiar"}` | Challenges the current bid. Not allowed before the round's first bid. |
| `{"type": "callSpotOn"}` | Only when `spotOn` is on. Claims the bid is exactly right. Not allowed before the first bid. |

| Error | When |
| --- | --- |
| `NOT_YOUR_TURN` | It is another player's turn. |
| `INVALID_ACTION` | Bad or non-raising bid; a call with no bid yet; `callSpotOn` while disabled; outside `bidding`; unknown `type`. |

**Rules**
- Every round, each player still in the game rolls their dice in secret (server rng). The first
  round is opened by a random player (server rng).
- Turns go round the table in join order, skipping eliminated players. Each turn is a bid or a call.
- **Liar:** all dice are revealed. If the actual count of the bid face (plus ones when
  `wildOnes` is on and the face is not 1) is **at least** the bid quantity, the caller loses a
  die; otherwise the bidder loses one.
- **Spot-on:** if the count is **exactly** the bid quantity, the caller gains a die (never above
  `startingDice`); otherwise the caller loses one.
- A player with 0 dice is eliminated. The player who lost the die starts the next round; if
  they were eliminated, the next player still in the game starts. After a successful spot-on,
  the caller starts.
- The game ends when one player is left.
- **Timers:**
  - Each turn lasts `DICE_TURN_MS` (30 s). When it runs out, the server makes the minimum legal
    bid for the player (`1 × 1` to open; otherwise the same quantity with the next face, or
    quantity + 1 with face 1 after a bid on sixes). If that would exceed the dice in play, it calls Liar instead.
  - After a call, the reveal is shown for `DICE_REVEAL_MS` (4 s), then the next round starts (or the game ends).

**View:**

```ts
type LiarsDiceView = {
  phase: 'bidding' | 'reveal' | 'done';
  round: number;                          // 1-based
  order: string[];                        // player ids in seat order
  myDice: number[];                       // your own dice only, sorted; [] once eliminated
  diceCounts: Record<string, number>;     // everyone's dice count (0 = eliminated)
  totalDice: number;
  eliminated: string[];                   // in elimination order
  currentPlayerId: string | null;         // null outside bidding
  isYourTurn: boolean;
  currentBid: {playerId: string; quantity: number; face: number} | null;
  history: {playerId: string; quantity: number; face: number; auto: boolean}[];  // this round
  settings: {startingDice: number; wildOnes: boolean; spotOn: boolean};
  deadline: number | null;                // epoch ms: turn end (bidding) or reveal end (reveal)
  lastReveal: Reveal | null;              // only during `reveal`
};

type Reveal = {
  round: number;
  call: 'liar' | 'spotOn';
  callerId: string;
  bid: {playerId: string; quantity: number; face: number};
  dice: Record<string, number[]>;         // every player still in the round
  actual: number;                         // dice matching the bid (wild ones included)
  loserId: string | null;                 // lost a die
  gainerId: string | null;                // gained a die (spot-on)
  eliminatedId: string | null;
  auto: boolean;                          // the server called on a timeout
};
```

Opponents' dice are **never** in a view except inside `lastReveal` during `reveal`.

**Events:**

| kind | data |
| --- | --- |
| `reveal` | `Reveal` (above) |
| `gameOver` | see 6.2 |

**Results:** placement by elimination order: the last player standing is 1st, the first player
out is last. `score` is the number of players they outlasted (`n − placement`), for display.

### 7.6 `name_it`: Name It Survival

**Players:** 3–10. **Settings** (defaults shown):

```json
{"turnSeconds": 10, "challenges": true, "allowCustomTopics": false}
```

| Setting | Values | Notes |
| --- | --- | --- |
| `turnSeconds` | integer `5`–`30` | Time per turn. The default comes from `NAMEIT_TURN_MS`. |
| `challenges` | boolean | Enables the `challenge` and `vote` actions. |
| `allowCustomTopics` | boolean | Off: the chooser must pick one of the `suggestions`. On: a typed topic is also accepted. |

**Actions:**

| Action | Who | Rules |
| --- | --- | --- |
| `{"type": "chooseTopic", "topic": string}` | the topic chooser, while `topicSelect` | Trimmed. One of the `suggestions`; or, with `allowCustomTopics`, any 1–40 characters from `NICKNAME_ALLOWED_PATTERN`. |
| `{"type": "submitAnswer", "text": string}` | the current player, while `turn` | Trimmed, 1–40 characters, and it must still have letters or digits after normalization. |
| `{"type": "challenge"}` | any alive player except the answerer | Only for the **latest** answer, within `NAMEIT_CHALLENGE_WINDOW_MS` (5 s) of it, while `turn`. |
| `{"type": "vote", "valid": boolean}` | each voter once, while `challenge` | Voters are the alive players except the answerer and the challenger. |

| Error | When |
| --- | --- |
| `NOT_YOUR_TURN` | `chooseTopic` from a non-chooser or outside `topicSelect`; `submitAnswer` when it is not your turn. |
| `INVALID_ACTION` | Bad topic (or a typed topic while `allowCustomTopics` is off) or bad answer; challenge outside the window, of your own answer, by an eliminated player, or with challenges off; vote by a non-voter, twice, or not a boolean; game over; unknown `type`. |

**Rules**
- The first topic is chosen by the **first player in seat order** (the room creator). The module
  does not know who the current host is.
- The chooser sees `NAMEIT_TOPIC_SUGGESTIONS` (5) random topics from `content/topics.json` and
  must pick one; a typed topic is accepted only when `allowCustomTopics` is on. After
  `NAMEIT_TOPIC_MS` (30 s) a random suggestion is used.
- Players answer in seat order, skipping eliminated players. The chooser of the first topic
  starts. An accepted answer passes the turn and restarts the timer.
- A player is **out** when they:
  - time out (`turnSeconds`);
  - repeat an answer (compared after normalization: lowercase, trim, strip a leading "the",
    drop punctuation and spaces; the repeat is not added to `used`);
  - lose a challenge.
- **Challenges:** a challenge pauses the current turn timer and opens a vote for
  `NAMEIT_VOTE_MS` (8 s). The vote closes early once every voter has voted. A strict majority
  of Invalid votes eliminates the answerer. Ties and no votes keep the answer. With only two
  players alive there are no voters, so the answer stays. If the answer stays, the paused turn
  resumes with the time it had left.
- When a player is out, the used list resets and they choose the next topic once (same 30 s
  fallback), then spectate. The next alive player after them in seat order starts.
- The last player left wins.

**View:**

```ts
type NameItView = {
  phase: 'topicSelect' | 'turn' | 'challenge' | 'done';
  topic: string | null;                    // null while a topic is being chosen
  topicChooserId: string | null;           // set during topicSelect
  isTopicChooser: boolean;
  suggestions: string[];                   // during topicSelect, otherwise []
  topicDeadline: number | null;            // epoch ms (topicSelect)
  order: string[];                         // seat order
  alive: string[];
  eliminated: string[];                    // in elimination order
  currentPlayerId: string | null;
  isYourTurn: boolean;
  turnDeadline: number | null;             // null while paused by a challenge
  pausedMs: number | null;                 // turn time left while a challenge runs
  used: {playerId: string; text: string}[];             // this topic, oldest first
  challengeWindow: {answerIndex: number; until: number} | null;  // latest answer
  challengeWindowMs: number;               // 5000
  canChallenge: boolean;                   // you may challenge the latest answer now
  challenge: {
    answerIndex: number;
    answererId: string;
    challengerId: string;
    text: string;
    deadline: number;                      // vote closes (epoch ms)
    voterIds: string[];
    votedCount: number;                    // how many voted; never who voted what
    canVote: boolean;
    hasVoted: boolean;                     // your own status only
  } | null;
  lastElimination: {playerId: string; reason: 'timeout' | 'duplicate' | 'challenge'; text: string | null} | null;
  settings: {turnSeconds: number; challenges: boolean; allowCustomTopics: boolean};
};
```

Votes are secret until the vote closes; they appear only in the `challengeResult` event.

**Events:**

| kind | data |
| --- | --- |
| `challengeResult` | `{answererId, challengerId, text, votes: Record<playerId, boolean>, validVotes, invalidVotes, valid: boolean}` (`valid: true` = the answer stays) |
| `eliminated` | `{playerId, reason: 'timeout' \| 'duplicate' \| 'challenge', text: string \| null, topic: string \| null}` |
| `gameOver` | see 6.2 |

**Results:** placement by elimination order: the last survivor is 1st, the first player out is
last. `score` is the number of players they outlasted (`n − placement`), for display.

## 8. Account HTTP API

Optional permanent accounts. Guests never need any of this. Plain JSON over HTTP under
`/api/auth/` and `/api/me/`; send `Content-Type: application/json`. Authenticated requests carry
`Authorization: Bearer <token>` (allowed by CORS from `CORS_ALLOWED_ORIGINS`). No cookies or
CSRF tokens are involved.

### 8.1 Tokens

| Item | Value |
| --- | --- |
| Format | JWT, HS256, signed with the server's `SECRET_KEY` |
| Claims | `{sub: user id (string), iat, exp}` |
| Lifetime | `AUTH_TOKEN_DAYS` (30) days from login or registration; no refresh |
| Logout | Client-side only: forget the token. Tokens are stateless, so there is no server logout. |
| Invalid when | expired, badly signed, or the account was disabled or deleted |

Store the token on the device (e.g. localStorage) and send it as `authToken` on
`room:create` / `room:join` (4.1). Treat the token as opaque.

### 8.2 Types

```ts
type AccountProfile = {          // only ever sent to the account holder
  username: string;
  nickname: string;
  color: string;
  avatar: Avatar;                // fixed forever at registration
  type: 'registered';
  createdAt: number;             // epoch ms
};

type AccountStats = {            // same shape as the guest Stats kept in the browser
  gamesPlayed: number;
  wins: number;
  byGame: Record<GameId, {played: number; wins: number}>;
};

type ApiError = {error: {code: string; message: string; fields?: Record<string, string>}};

type MyStats = {                 // GET /api/me/stats; computed by the server from PlayerStats
  totals: GameTotals;
  favoriteGame: GameId | null;   // most played; ties: more wins, then game id A-Z; null if none
  perGame: (GameTotals & {gameId: GameId})[];  // games with played > 0, in favorite order
  minGamesForRate: number;       // DASHBOARD_MIN_GAMES_FOR_RATES
};

type GameTotals = {
  played: number;
  wins: number;                  // placement-1 finishes (ties share the win)
  losses: number;                // played - wins
  winRate: number | null;        // wins / played (0..1, 4 decimals); null while played < minGamesForRate
};

type RecentPlayer = {            // GET /api/me/recent-players
  tag: string;                   // public code, shown as "#" + tag
  nickname: string;              // their current saved nickname
  avatar: Avatar;
  color: string;
  lastPlayedAt: string;          // ISO-8601 UTC: end of the newest shared completed game
  gamesTogether: number;         // shared completed games within the window
  lastGameId: GameId;            // the game of that newest shared session
  relationship: 'none' | 'friends' | 'requested' | 'incoming';  // requested: you asked them
};
```

### 8.3 Endpoints

**`POST /api/auth/register`** → `201 {token, profile}`

```json
{"username": "sam_1", "password": "correct horse battery",
 "profile": {"nickname": "Sam", "color": "#F1C40F", "avatar": {"style": "cutouts", "seed": "9c41e07b"},
             "stats": {"gamesPlayed": 4, "wins": 2, "byGame": {"rps": {"played": 4, "wins": 2}}}}}
```

```json
{"token": "eyJhbGciOi...", "profile": {"username": "sam_1", "nickname": "Sam", "color": "#F1C40F",
 "avatar": {"style": "cutouts", "seed": "9c41e07b"}, "type": "registered", "createdAt": 1792324569015,
 "avatarLockedUntil": null}}
```

- `username` matches `USERNAME_PATTERN` (3–20 letters, digits, `_`) and is unique **ignoring case**.
- `password`: at least `PASSWORD_MIN_LENGTH` (8) characters and passes Django's validators
  (not too common, not all digits, not too similar to the username).
- `profile.nickname` / `profile.color`: the same rules as room profiles (5).
- `profile.avatar` (optional): the guest's current avatar is **claimed** (kept until the player changes it, see `PATCH /api/auth/profile`) when
  valid (5.1 rules). Missing or invalid: a random one is assigned. Send it so the player keeps
  the face they know.
- `profile.stats` (optional): the guest's browser stats, imported for fun. Only `byGame` is read.
  Accepted only if every entry is a known `GameId` with integers `0 ≤ wins ≤ played` and the
  total played is at most `STATS_MAX_IMPORT_GAMES` (500); otherwise all of it is ignored and the
  account starts at zero. The registration still succeeds either way.

**`POST /api/auth/login`** `{"username", "password"}` → `200 {token, profile, stats}`

The username is matched ignoring case. Wrong username and wrong password get the **same**
`401 INVALID_CREDENTIALS` response.

**`GET /api/auth/me`** (Bearer) → `200 {profile, stats, tag, createdAt}`

Use it on startup to check a stored token and refresh the saved profile and stats. `tag` is the
account's public tag (8.6) and `createdAt` the registration time as ISO-8601 UTC
(`"2026-10-27T11:31:05Z"`); `profile.createdAt` stays epoch ms. `Cache-Control: no-store`.

**`GET /api/me/stats`** (Bearer) → `200 MyStats` (8.2)

The account's own totals, favorite game and per-game rows from the same counters as `stats`
(8.4). The client never computes any of these. `Cache-Control: no-store`.

```json
{"totals": {"played": 12, "wins": 5, "losses": 7, "winRate": 0.4167}, "favoriteGame": "rps",
 "perGame": [{"gameId": "rps", "played": 8, "wins": 4, "losses": 4, "winRate": 0.5},
             {"gameId": "hangman", "played": 4, "wins": 1, "losses": 3, "winRate": null}],
 "minGamesForRate": 5}
```

**`GET /api/me/recent-players`** (Bearer) → `200 {players: RecentPlayer[]}` (8.2)

Up to `RECENT_PLAYERS_MAX` (30) distinct **registered** players who finished a **completed**
game with the account holder that ended in the last `RECENT_PLAYERS_DAYS` (30) days, newest
first. Never the account holder, guests, disabled accounts, deleted accounts, or anyone blocked
in either direction (8.7). No login
usernames, ids, emails or guest keys are ever included. `Cache-Control: no-store`.

```json
{"players": [{"tag": "K7M2QX", "nickname": "Ann", "avatar": {"style": "cutouts", "seed": "1b2c3d4e"},
              "color": "#E74C3C", "lastPlayedAt": "2026-10-26T18:04:11Z", "gamesTogether": 3,
              "lastGameId": "liars_dice", "relationship": "none"}]}
```

**`PATCH /api/auth/profile`** (Bearer) `{"nickname"?, "color"?, "avatar"?}` → `200 {profile}`

Only the fields present change. The username cannot be changed. Rooms already joined keep the
old values; the change applies from the next `room:create` / `room:join`.

- `avatar` is `{style, seed}` (validated like registration: `style` in `AVATAR_STYLES`, `seed`
  matching `AVATAR_SEED_PATTERN`). The client picks it, e.g. by shuffling random ones.
- A **new** avatar can be saved at most once every `AVATAR_CHANGE_DAYS` (30) days. While
  locked, a request with a different avatar is refused with `409 AVATAR_LOCKED`
  (`fields.avatar` set) and **nothing** in it is saved. Sending the current avatar again is
  not a change: allowed, and the lock does not restart. A new account can change it at once.
- Every `profile` object (register, login, me, this endpoint) has `avatarLockedUntil`: epoch
  ms of the next allowed change, or `null` when a change is allowed now.

**`DELETE /api/auth/account`** (Bearer) `{"password"}` → `200 {"ok": true}`

Deletes the account, its saved profile and its stats, plus its friendships, friend requests and
blocks (8.7). Reports by or about the account are kept for staff with the account link removed
and the reported nickname snapshot kept. The token stops working.

### 8.4 Stats

Server-side stats count finished games only: `played + 1` for every registered player in the
results, `wins + 1` for placement 1 (ties share the win). Guests in the same game are not
counted anywhere on the server.

### 8.5 Errors

Every error response is `{"error": {"code", "message", "fields"?}}`. `fields` maps a request
field (`username`, `password`, `nickname`, `color`, `avatar`) to a message to show next to it.

| Status | `code` | When |
| --- | --- | --- |
| 400 | `INVALID_INPUT` | Missing, malformed or weak input, or a body that is not a JSON object. Has `fields` when tied to fields. |
| 401 | `INVALID_CREDENTIALS` | Login failed (one generic message), or wrong password on account deletion. |
| 401 | `UNAUTHORIZED` | Missing, invalid or expired Bearer token, or a disabled or deleted account. Forget the token and offer login. |
| 405 | `METHOD_NOT_ALLOWED` | Wrong HTTP method for the endpoint. |
| 409 | `AVATAR_LOCKED` | `PATCH /api/auth/profile` with a new avatar within `AVATAR_CHANGE_DAYS` of the last change. `fields.avatar` is set. |
| 409 | `USERNAME_TAKEN` | Registration with a username already in use (ignoring case). `fields.username` is set. |
| 429 | `RATE_LIMITED` | More than `AUTH_RATE_LIMIT_PER_MIN` (10) register or login requests per minute from one IP. |

Example:

```json
{"error": {"code": "INVALID_INPUT", "message": "Some fields need fixing.",
           "fields": {"password": "This password is too common."}}}
```

### 8.6 Tags

Every registered account has a public tag: `TAG_LENGTH` (6) characters from `TAG_ALPHABET`
(`ABCDEFGHJKLMNPQRSTUVWXYZ23456789`, no I, O, 0 or 1), shown as `#K7M2QX`. It is random
(`secrets`), unique, assigned at registration, never changes (not even with the nickname), and
is never reused after the account is deleted. It is not the login username and never contains
it. It is returned only by `GET /api/auth/me`, `GET /api/me/recent-players` and the friends
endpoints (8.7), and over the WebSocket only in the social pushes of section 9, never in
`room:state`.

### 8.7 Friends, blocks, reports and settings

Registered accounts only (guests have no token). Every endpoint needs the Bearer token, answers
`Cache-Control: no-store` and uses the error format of 8.5. Players are always named by their
public tag; no response contains a login username, user id, profile id or email. A tag in a
body or URL is normalized: surrounding spaces and a leading `#` are dropped and it is
uppercased (`"#k7m2qx"` → `"K7M2QX"`). A value that cannot be a tag is `400 INVALID_INPUT`.

```ts
type PlayerCard = {tag: string; nickname: string; avatar: Avatar; color: string};
type FriendStatus = 'online' | 'in_lobby' | 'in_game' | 'busy' | 'offline';
type Friend = PlayerCard & {status: FriendStatus};
type FriendRequest = PlayerCard & {requestId: number; createdAt: string};  // ISO-8601 UTC
type PresenceMode = 'online' | 'busy' | 'offline';                        // offline = appear offline
type ReportReason = 'harassment' | 'inappropriate_name_or_avatar' | 'cheating' | 'spam' | 'other';
```

**`GET /api/friends`** → `200 {friends: Friend[], incoming: FriendRequest[], outgoing: FriendRequest[], blocked: PlayerCard[]}`

`friends` are sorted by status (online, in_lobby, in_game, busy, offline), then nickname.
Requests and blocks are newest first. In requests, the card is the *other* player. Disabled
accounts are left out of `friends`, `incoming` and `outgoing`.

**`POST /api/friends/requests`** `{"tag"}` → `200 {"status": "requested" | "friends"}`

If that player already sent you a request, it is accepted instead (`"friends"`). If either of
you blocked the other, or their account is disabled, the answer is `{"status": "requested"}`
exactly as for a real request, but nothing is created.

| Status | `code` | When |
| --- | --- | --- |
| 400 | `SELF` | Your own tag. |
| 404 | `NOT_FOUND` | No account has that tag. |
| 409 | `ALREADY_FRIENDS` | You are friends already. |
| 409 | `ALREADY_REQUESTED` | Your request to them is still pending. |
| 409 | `LIMIT_REACHED` | You (or they, on an auto-accept) have `MAX_FRIENDS` (100) friends, you have `MAX_PENDING_OUTGOING` (30) requests waiting, or they have `MAX_PENDING_INCOMING` (50). |
| 429 | `RATE_LIMITED` | More than `FRIEND_REQUESTS_PER_HOUR` (20) attempts in the last hour. |

**`POST /api/friends/requests/<requestId>/accept`** → `200 {"status": "friends"}` ·
**`POST /api/friends/requests/<requestId>/decline`** → `200 {"ok": true}`

Recipient only; anyone else (or a request that is gone) gets `404 NOT_FOUND`. Accepting can
fail with `409 LIMIT_REACHED` when either side has `MAX_FRIENDS`. Declining is not told to the
sender.

**`DELETE /api/friends/requests/<requestId>`** → `200 {"ok": true}`: cancel your own outgoing
request (`404 NOT_FOUND` otherwise).

**`DELETE /api/friends/<tag>`** → `200 {"ok": true}`: remove a friend. The other player is not
told; you simply disappear from each other's lists. `404 NOT_FOUND` if you are not friends.

**`GET /api/friends/<tag>/profile`** → `200 PlayerCard & {memberSince: string, stats: MyStats}`

Friends only: anyone else, including unknown tags and disabled accounts, gets
`403 FORBIDDEN` and no stats. `memberSince` is ISO-8601 UTC; `stats` has the shape of
`GET /api/me/stats`.

**`POST /api/blocks`** `{"tag"}` → `200 {"ok": true}` · **`DELETE /api/blocks/<tag>`** → `200 {"ok": true}`

Blocking is silent and idempotent. It removes any friendship and pending requests in both
directions. From then on the two players are left out of each other's friend lists, requests
and recent players, and cannot invite each other (9.4). Blocks never affect room membership.
Errors: `400 SELF`, `404 NOT_FOUND` (unknown tag; on DELETE also "not blocked").

**`POST /api/reports`** `{"tag", "reason", "note"?}` → `200 {"ok": true}`

`reason` is one of `REPORT_REASONS`. `note` is optional text for staff only, at most
`REPORT_NOTE_MAX` (200) characters; line breaks become spaces and control or invisible
formatting characters are removed. It is never shown to other players. Each reporter may file
`REPORTS_PER_DAY` (10) new reports per 24 hours (`429 RATE_LIMITED`). Reporting the same player
again within `REPORT_DUPLICATE_WINDOW_HOURS` (24) while your report is still open is accepted
but merged into it (a missing note is filled in) and does not count toward the limit. Errors:
`400 INVALID_INPUT` (`fields.reason` or `fields.note`), `400 SELF`, `404 NOT_FOUND`.

**`GET /api/me/settings`** → `200 {"presence": PresenceMode}` ·
**`PATCH /api/me/settings`** `{"presence"}` → `200 {"presence": PresenceMode}`

The default is `"online"`. `"busy"` shows friends a busy status and `"offline"` makes the
account appear offline. An unknown value is `400 INVALID_INPUT` with `fields.presence`.

## 9. Friends, presence and invites (WebSocket)

For registered accounts. Guests never send or receive any of this, and nothing here changes
`room:state`. Pushes carry a tag only to that account's friends (and, with a friend request or
an invite, to its recipient). No push or ack carries a login username, user id, profile id,
email, room contents, or (except the `invite:accept` ack) a room code.

### 9.1 `auth:hello`

```json
{"id": 1, "type": "auth:hello", "payload": {"authToken": "eyJhbGciOi..."}}
```

Ack: `{"presence": PresenceMode}` (the saved setting, 8.7). Binds this connection to the account
for presence and invites, then pushes `friends:snapshot` and an `invite:received` for every
invite still pending for the account. Send it after **every** (re)connect while signed in,
before anything else. A missing, invalid or expired token, or a disabled or deleted account,
is `UNAUTHORIZED` and the connection stays (or becomes) a guest connection. `room:create` and
`room:join` with `authToken` work exactly as before and do not bind presence.

### 9.2 Status

| Status | When |
| --- | --- |
| `offline` | No signed-in connection, or the presence setting is `"offline"` (appear offline). |
| `busy` | The presence setting is `"busy"`. |
| `in_game` | Seated in a room whose status is `"playing"` and still in the game (`inGame`). |
| `in_lobby` | Seated in a room in any other state (including after quitting a running game). |
| `online` | Otherwise. |

An account is connected while it has at least one signed-in connection. When the last one
closes it keeps its status for `PRESENCE_OFFLINE_DELAY_MS` (5000), so a quick reconnect
causes no offline flicker. Changing the setting with `PATCH /api/me/settings` applies at once.

### 9.3 Pushes

| `type` | `data` | To |
| --- | --- | --- |
| `friends:snapshot` | `{friends: {tag, status}[]}` | The connection, after `auth:hello`. |
| `friends:presence` | `{tag, status}` | The account's signed-in friends, when its status changes; also to both sides right after they become friends. |
| `friends:request` | `{request: FriendRequest}` (8.7) | The recipient, when a request arrives. |
| `friends:accepted` | `{tag, nickname}` | **Both** new friends (each gets the other's card), on accept or auto-accept. |
| `friends:removed` | `{tag}` | Both former friends, when either removes or blocks the other; every friend of an account that is disabled or deleted. Show nothing; just drop the row. |
| `invite:received` | `{inviteId, fromTag, fromNickname, fromAvatar, gameId, expiresAt, serverNow}` | Every signed-in connection of the recipient. `gameId` is the selected game or `null`. `expiresAt` and `serverNow` are server epoch ms: count down `expiresAt - serverNow` from arrival. **No room code.** |
| `invite:expired` | `{inviteId}` | The recipient, when the invite ran out (`INVITE_TTL_MS`, 120000) or its room started a game, closed, filled, or the sender left, or a newer invite replaced it. |
| `invite:cleared` | `{inviteId}` | The recipient's *other* connections, after they accepted or declined it on one. Remove the banner silently. |

### 9.4 Invites

Invites live in server memory only: they expire after `INVITE_TTL_MS` and a server restart
drops them all.

**`invite:send`** `{tag}` → ack `{}`. The sender's seat must be registered, in a room in the
`lobby` with space (fewer seated players than `MAX_PLAYERS` and the selected game's maximum),
and the target a friend whose status is exactly `online`. Errors, in the order checked:
`NOT_IN_ROOM`, `INVALID_ACTION` (guest seat, or the room is not in the lobby), `ROOM_FULL`,
`NOT_FRIENDS`, `RATE_LIMITED` (the same friend again within `INVITE_COOLDOWN_MS` (30000), or more
than `INVITES_PER_MINUTE` (10) per minute), `TARGET_UNAVAILABLE`. A friend holds at most
`MAX_PENDING_INVITES_PER_USER` (5) pending invites; the oldest is expired to make room, and a new
invite from the same sender replaces their older one.

**`invite:accept`** `{inviteId}` → ack `{code}`. Recipient only (on a connection that sent
`auth:hello`), before expiry, with the room still in the lobby and not full, and no block
between the two. The invite is used up; then join with the normal `room:join` and that code.
Errors: `INVITE_INVALID`, `INVITE_EXPIRED`, `ROOM_FULL`.

**`invite:decline`** `{inviteId}` → ack `{}` always. The sender is never told.

### 9.5 Actions on a player in your room

For the lobby and results screens. Both seats must be in the sender's room (`NOT_IN_ROOM`
when the sender has none; `INVALID_ACTION` when the target is not in it or is the sender), and
the sender's seat must be registered (`INVALID_ACTION` otherwise). They use the same rules,
limits and generic answers as the HTTP API (8.7), so a block is never revealed.

| Request | Payload | Ack | Notes |
| --- | --- | --- | --- |
| `friends:requestByPlayer` | `{playerId}` | `{status: "requested" \| "friends"}` | Target must be registered (`INVALID_ACTION`). |
| `player:block` | `{playerId}` | `{}` | Target must be registered. Never changes the room. |
| `player:report` | `{playerId, reason, note?}` | `{}` | Guests may be reported: their pseudonymous guest key and nickname are stored. The room code and game are stored with the report for staff. |

## 10. Admin reports API (staff)

Part of the staff JSON API under `/api/admin/` used by the `/admin` dashboard. Same rules as the
rest of it: staff only (anonymous `401`, non-staff `403`, both with `loginUrl`), the Django admin
session cookie, CSRF token from `GET /api/admin/session` in `X-CSRFToken` on every POST, and
`X-Robots-Tag: noindex, nofollow`. The report endpoints also send `Cache-Control: no-store`.
Resolving and dismissing are written to the Django admin log (`LogEntry`), like disabling and
deleting accounts. Staff may see login usernames here; passwords, tokens and emails are never
included.

```ts
type ReportPerson = {
  kind: 'registered' | 'guest' | 'deleted';  // deleted: the account is gone, only the snapshot is left
  userId: number | null;         // registered: link to /admin/users/u/<userId>
  guestKey: string | null;       // guest: link to /admin/users/g/<guestKey>
  shortKey?: string;             // guest only
  name: string;
  nickname: string;              // reported: the nickname when reported; reporter: current nickname
  tag: string | null;            // registered only
  username: string | null;       // registered only
};

type AdminReport = {
  id: number;
  createdAt: string;             // ISO-8601
  status: 'open' | 'resolved' | 'dismissed';
  reason: ReportReason;          // 8.7
  note: string;                  // the reporter's note ("" if none)
  reporter: ReportPerson | null; // null once the reporter's account is deleted
  reported: ReportPerson;
  roomCode: string | null;       // set for reports made inside a room (9.5)
  gameId: GameId | null;
  game: {id: GameId; name: string} | null;
  resolvedBy: string | null;     // staff username
  resolvedNote: string;
  resolvedAt: string | null;
};
```

**`GET /api/admin/reports?status=&reason=&page=`** →
`200 {page, numPages, count, pageSize, query: {status, reason}, statuses, reasons, openReports, results: AdminReport[]}`

Open reports first, then newest first. Unknown filter values are ignored. `pageSize` is
`DASHBOARD_PAGE_SIZE` (50).

**`POST /api/admin/reports/<id>/resolve`** `{"action": "resolved" | "dismissed", "note"?}` →
`200 {ok: true, report: AdminReport, openReports}`

`note` is at most 500 characters (control characters removed). Errors: `400 INVALID_INPUT`,
`403 FORBIDDEN` (staff without the "change report" permission; superusers have it), `404
NOT_FOUND`, `409 NOT_OPEN` (already resolved or dismissed).

**Counts elsewhere:** `GET /api/admin/session` and `GET /api/admin/overview` include
`openReports` (never cached; `null` in the session for non-staff). The user detail endpoints
(`/api/admin/users/u/<id>` and `/users/g/<key>`) include `reportsAgainst: {total, open}`.

## 11. Guest free games

Guests get `GUEST_FREE_GAMES` (7) games per `GUEST_WINDOW_MS` (7200000, 2 hours), enforced by
the server per guest (by profile id). Registered seats are never counted or locked.

- **Window:** starts at the guest's first counted game. Once `now >= windowStart +
  GUEST_WINDOW_MS`, the next counted game starts a new window. A guest is **locked** while
  `plays >= GUEST_FREE_GAMES` in the current window; `lockedUntil = windowStart + GUEST_WINDOW_MS`.
- **Counting:** at `game:start`, once per guest who plays in it. Forfeits and host-ended games
  are not refunded; a running game is never interrupted.
- **`game:start`:** locked guests are left out (`inGame: false`, like a forfeited player) and
  everyone else is counted. If fewer than the game's minimum remain, the start fails with
  `GUEST_LIMIT`, `data: {nicknames: string[]}` (the locked guests), and nobody is counted.
- **New seats:** `room:create` and `room:join` for a new seat by a locked guest fail with
  `GUEST_LIMIT`, `data: {lockedUntil}`. Reclaiming a seat (`roomToken` or account) always works.
- **`Player.locked`:** true for a guest seat found locked at the last `game:start` (or locked by
  it). Locked players are left out of `readyCheck`.
- If the quota store fails, play is allowed (fail open) and the error is logged.

**`guest:quota`** `{profile: {id}}` → ack `{remaining, limit, lockedUntil, serverNow}`
(`lockedUntil` is epoch ms or `null`). No seat needed (for the home screen).

**Push `guest:quota`** `{remaining, limit, lockedUntil, serverNow}`: after each game start, to
every guest who was counted or left out. Count down `lockedUntil - serverNow` from arrival.
