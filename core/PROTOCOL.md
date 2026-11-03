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
>
> **Additions (solo games, part 1):** additive only. Registered players can play
> `tic_tac_toe` and `connect_four` alone against a bot (section 16): new requests `solo:start`,
> `solo:again`, `solo:quit`; `RoomPublic.solo` and `soloVariant`; `Player.bot` (and
> `Player.type` `"bot"`, `avatar: null` for the bot); `soloResult` in solo `game:view`s;
> `GET /api/solo/records`.
>
> **Additions (staying seated):** additive only. New request `room:resume` (4.11), error code
> `ALREADY_IN_GAME`, the one-seat rule and the takeover notice (6.3), and
> `HOST_OFFLINE_TRANSFER_MS` (45 s) for the host takeover delay.
>
> **Additions (solo games, part 2):** additive only. Solo challenges `guess_race`, `name_it` and
> `hangman` (section 16.1): new `solo:start` variants, the `run_over` soloResult and their views.
>
> **Additions (solo games, part 3):** additive only. Solo `dots_and_boxes` (variant `{difficulty,
> size}`) and `penalty_kick`; `penalty_kick` accepts an optional `diveGraceMs` setting (default
> `PENALTY_DIVE_GRACE_MS`, so multiplayer is unchanged).

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
| `ROOM_NOT_FOUND` | No room with that code. A solo room (16) answers this to everyone but its owner. |
| `ROOM_FULL` | The room already has `MAX_PLAYERS` (10) players. |
| `NAME_TAKEN` | Reserved. Duplicate nicknames are auto-suffixed (`Sam`, `Sam2`, `Sam3`), so this is not normally sent. |
| `NOT_HOST` | Host-only request sent by a non-host. |
| `NOT_YOUR_TURN` | A game action out of turn. |
| `INVALID_ACTION` | Invalid payload, profile, settings, or game move. Also used for an unexpected server error ("Something went wrong."). |
| `GAME_IN_PROGRESS` | Joining a room mid-game without a valid `roomToken` for a seat; `solo:again` while the solo game still runs (16). |
| `RATE_LIMITED` | More than `ACTION_RATE_LIMIT_PER_SEC` (5) game actions per second on this connection, or a `room:react` within `REACTION_COOLDOWN_MS` of the player's previous one. |
| `NOT_IN_ROOM` | Request needs a room but this connection has no seat (never joined, left, or was detached). |
| `UNKNOWN_EVENT` | `type` is not a known request type. |
| `BAD_MESSAGE` | Frame is not valid JSON, or the envelope is malformed. |
| `UNAUTHORIZED` | `auth:hello` with a missing, invalid or expired token, or a disabled or deleted account (9.1). |
| `NOT_FRIENDS` | `invite:send` to someone who is not your friend (or an unknown tag). |
| `GUEST_LIMIT` | A guest out of free games (11): `room:create` / `room:join` for a new seat, with `data: {lockedUntil}`; `game:start` when too few players are left, with `data: {nicknames}`. |
| `GAME_DISABLED` | `room:selectGame`, `game:start` or `solo:start` for a game staff turned off (13). |
| `ALREADY_IN_GAME` | `room:create` or `room:join` (new seat) while playing a running game in another room, with `data: {code}` (6.3). |
| `NOT_ENOUGH_BRAG` | Joining or setting a Brag coin stake without the coins, or too few players able to pay at `game:start` (17), `data: {balance, stake}`. |
| `STAKE_NOT_AGREED` | `game:start` while too few players joined the stake (17), `data: {joined, needed}`. |
| `REGISTERED_ONLY` | A guest touching a registered-only game (12): `room:selectGame` or `game:start` by a guest host; `game:start` when too few registered players are seated, with `data: {nicknames}` (the guests); a `game:action` (including `watch`) from a guest while one runs; `solo:start` from a guest (16). |
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
room `finished`), `GAME_IN_PROGRESS`, `REGISTERED_ONLY` (a guest host picking a registered-only
game, 12), `GAME_DISABLED` (a game staff turned off, 13).

Picking a different game, or changing at least one stored setting value, clears every ready flag
(4.9) and sends `ready_reset` to the players whose flag was set. Sending the same game with
settings that validate to the same values changes nothing.

### 4.6 `game:start` (host only)

Payload: `{}`. Only in `lobby`. Requires a selected game and a seated-player count within its
min/max (offline players count and take part). Everyone receives `room:state` (status `playing`)
then their first `game:view`.
Ack data: `{}`. Errors: `NOT_IN_ROOM`, `NOT_HOST`, `INVALID_ACTION` (no game selected, wrong
player count, room `finished`), `GAME_IN_PROGRESS`, `GUEST_LIMIT` (11), `REGISTERED_ONLY` (12),
`GAME_DISABLED` (13).
Locked guests (11) sit the game out (`inGame: false` from the start) and are not counted in the
player count. In a registered-only game (12) every guest sits it out the same way.

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

### 4.11 `room:resume`

Finds the caller's own seat after a lost connection or an app restart. Payload: `{authToken}` for
an account (its seat in any room but a solo one), or `{tokens: [{code, roomToken}]}` for a guest
(the stored tokens, up to 20; the first that still holds a live seat wins). Ack data:
`{resume: {code, roomToken, status, hostNickname, playerCount} | null}` — null when there is no
seat or its room closed. Nothing is ever said about rooms the caller is not seated in. The client
then sends `room:join` with that `code` and `roomToken`. Rate limited like game actions
(`RATE_LIMITED`).

## 5. Types

```ts
type GameId = 'rps' | 'guess_race' | 'hangman' | 'dots_and_boxes' | 'liars_dice' | 'name_it'
  | 'tic_tac_toe' | 'connect_four' | 'penalty_kick' | 'checkers';

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
  type: 'guest' | 'registered' | 'bot';  // for a badge; no username or account id is ever exposed
  nickname: string;         // may carry a suffix: "Sam2"
  color: string;
  avatar: Avatar | null;    // assigned by the server when the seat is created; null only for a bot
  online: boolean;
  joinedAt: number;         // epoch ms
  ready: boolean;           // lobby ready check (4.9); always false for the host
  locked: boolean;          // a guest out of free games (11); always false for registered seats
  registeredOnlyBlocked: boolean; // a guest while the selected or running game is registered-only (12)
  bot: boolean;             // the bot of a solo room (16); always nickname "Bot", never a person
};

type RoomStatus = 'lobby' | 'playing' | 'between_rounds' | 'finished';

type RoomPublic = {
  code: string;
  hostId: string;
  status: RoomStatus;
  players: Player[];        // seat (join) order
  selectedGame: GameId | null;   // null for a guest while a registered-only game is selected (12)
  settings: Record<string, unknown> | null; // null exactly when selectedGame is hidden that way
  scoreboard: Record<string, number>;   // playerId -> session points, up to 2 decimals (only players with points recorded)
  wins: Record<string, number>;         // playerId -> games won (placement 1) this session
  readyCheck: { count: number; total: number } | null;  // 4.9; null while no game is selected
  disabledGames: GameId[];  // games staff turned off (13), sorted; clients hide them
  solo: boolean;            // a solo room (16)
  soloVariant: { difficulty: 'easy' | 'medium' | 'hard' } | null;  // null unless solo
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
  - when the host has been offline for more than `HOST_OFFLINE_TRANSFER_MS` (45 s) and someone
    is online. (`HOST_TRANSFER_MS` stays in the constants for older clients; the server no longer
    uses it.)
  A host who returns within that time keeps the role. A former host does not get it back.
- Reclaiming a seat from a new connection takes it over: the older connection gets the push
  `error` `{code: "NOT_IN_ROOM", message: "You signed in elsewhere.", data: {reason:
  "signed_in_elsewhere"}}` and must not rejoin on its own.
- **One seat at a time** (not counting solo rooms, 16): `room:create`, or `room:join` for a new
  seat, while the same account (or, for a guest, the same browser profile) is seated in another
  room first leaves that room the normal way (`room:leave`, with its usual events) when it is not
  playing a game there; if that player is in a running game there, the request fails with
  `ALREADY_IN_GAME`, `data: {code}`. The client offers "Return to game" or "Leave it" (a forfeit,
  through the usual `room:leave`).

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
| `game_unselected` | The (new) host. Host passed to a guest while a registered-only game was selected (12), or staff turned the selected game off (13); the selection is cleared. | `{reason: "registered_only" \| "disabled"}` |
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
| `tic_tac_toe` | Part 1A (series, 7.7) |
| `connect_four` | Part 1B (series, 7.7) |
| `penalty_kick` | Part 1B (series, 7.7) |
| `checkers` | Part 2A (series, 7.7) |

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

### 7.7 Series games: two-player games in matches and a bracket

`tic_tac_toe`, `connect_four`, `penalty_kick` and `checkers` share one wrapper: every game is a
two-player game played as best-of **matches** inside a knockout **bracket**. With 2 players
the bracket is a single match.

**Players:** 2–10.

**Bracket** (as in `rps`)
- Each bracket round pairs the players still in at random. An odd count gives one random
  player a bye, preferring players who have not had one. Matches of a round run at the same
  time; when they are all decided, winners advance to the next round.
- Match ids are `r{bracketRound}m{n}` (`r1m1`, `r1m2`, …). Seat 1 is `a`, seat 2 is `b`.

**Matches**
- A match is best of `bestOf` games (`1`, `3` or `5`): the first to `winsNeeded`
  (`bestOf // 2 + 1`) wins it. Games without a `bestOf` setting play one game per match.
- Seat 1 moves first in game 1; the first mover alternates every game, drawn games included.
- A drawn game does not count and is replayed (with the other player opening). After
  `MATCH_MAX_DRAWS` (3) draws the server decides the match at random: `coinFlip: true`.
- **AFK:** when a turn timer runs out, the server makes a random legal move for the player
  (`autoMove` event). `MATCH_AFK_TIMEOUTS_TO_FORFEIT` (3) timeouts in a row by one player lose
  them the match (`reason: 'afk'`); any move of their own resets the count.
- **Forfeit** (`game:quit`, leaving, offline timeout): a player in a live match loses it and
  the opponent advances (`reason: 'forfeit'`). A player waiting (bye or won match) leaves the
  bracket before the next pairing; a player already knocked out just becomes `inGame: false`.

**Spectating:** a player not in a live match (waiting or knocked out) is a spectator. Their
`match` is the public view of one live match: the one they chose with `watch`, else the
first live match (else their own last match, so a finished final stays on screen).
Spectator views never contain hidden information or per-player data such as legal moves.

**Actions** (on top of each game's own):

| Action | Who | Effect |
| --- | --- | --- |
| `{"type": "watch", "matchId": string}` | spectators only | Show that live match. No game effect, no event. |

| Error | When |
| --- | --- |
| `NOT_YOUR_TURN` | A game action from a player who is not in a live match; not your turn. |
| `INVALID_ACTION` | `watch` from a player in a live match, or for a match that is not live; the game's own errors. |

**View** (the shared shell; `game` is the game's own view, see each game):

```ts
type SeriesMatch = {
  id: string;
  a: string;
  b: string | null;                     // null for a bye
  phase: 'playing' | 'over';
  wins: Record<string, number>;         // games won in this match
  gameNo: number;                       // games started, draws included (1 = first game)
  draws: number;
  winner: string | null;
  reason: 'bye' | 'score' | 'forfeit' | 'afk' | 'coinFlip' | null;
  coinFlip: boolean;
  lastGame: {gameNo: number; result: 'winner' | 'draw'; winner: string | null; game: object} | null;
};

type SeriesView<G> = {
  phase: 'playing' | 'waiting' | 'out' | 'done'; // you: in a live match, through/bye, knocked out
  role: 'player' | 'spectator';
  bestOf: number;
  winsNeeded: number;
  bracketRound: number;
  matches: SeriesMatch[];               // the current bracket round
  liveMatches: string[];                // ids of matches still being played
  match: (SeriesMatch & {game: G}) | null; // yours, or the one you watch
  watching: string | null;              // spectators: the shown match id; players: null
  alive: string[];
  eliminated: string[];
  champion: string | null;
};
```

`lastGame` keeps the final public view of the match's previous game, so a board stays visible
after the next game has started.

**Events** (every game event carries `matchId`):

| kind | data |
| --- | --- |
| `bracketRound` | `{bracketRound, pairs: [a, b \| null][]}` |
| `autoMove` | `{matchId, playerId}`: the server moved for a timed-out player |
| `gameEnd` | `{matchId, gameNo, result: 'winner' \| 'draw', winner, game}` |
| `matchOver` | `{matchId, winnerId, loserId \| null, reason, coinFlip}` |
| `gameOver` | see 6.2 |

**Results:** placement by the bracket round a player lost in: champion 1st, runner-up 2nd,
losing semifinalists tied 3rd, and so on. `score` is matches won (byes don't count).

### 7.8 `tic_tac_toe`: Tic-Tac-Toe

A series game (7.7). **Settings** (defaults shown):

```json
{"bestOf": 3}
```

| Setting | Values | Notes |
| --- | --- | --- |
| `bestOf` | `1`, `3`, `5` | Games per match; first to the majority wins. |

**Action:** `{"type": "place", "cell": 0-8}` (cells row by row: 0–2 top, 3–5 middle, 6–8 bottom).

| Error | When |
| --- | --- |
| `NOT_YOUR_TURN` | It is your opponent's turn. |
| `INVALID_ACTION` | Cell not an integer 0–8 or already taken; unknown `type`. |

**Rules:** seat 1 is X, seat 2 is O; the game's first mover opens. Three in a row (across,
down or diagonal) wins; a full board without one is a draw. Each turn lasts `TTT_TURN_MS`
(15 s); a timeout places a random empty cell.

**Game view** (`match.game`):

```ts
type TicTacToeGame = {
  board: ('X' | 'O' | null)[];          // 9 cells
  marks: Record<string, 'X' | 'O'>;     // player id -> mark
  firstMover: string;
  turn: string | null;                  // null once the game is decided
  turnDeadline: number | null;          // epoch ms
  lastMove: number | null;              // cell
  winner: string | null;
  winningCells: number[] | null;
  // players in the match only:
  isYourTurn?: boolean;
  legalMoves?: number[];                // empty cells on your turn, else []
};
```

### 7.9 `connect_four`: Connect Four

A series game (7.7). **Settings** (defaults shown):

```json
{"bestOf": 3}
```

| Setting | Values | Notes |
| --- | --- | --- |
| `bestOf` | `1`, `3`, `5` | Games per match; first to the majority wins. |

**Action:** `{"type": "drop", "column": 0-6}`

| Error | When |
| --- | --- |
| `NOT_YOUR_TURN` | It is your opponent's turn. |
| `INVALID_ACTION` | Column not an integer 0–6 or full; unknown `type`. |

**Rules:** 7 columns × 6 rows; rows run top (0) to bottom (5) and a disc lands in the lowest
empty row of its column. Four in a row across, down or diagonally wins; a full board without
one is a draw. Each turn lasts `C4_TURN_MS` (20 s); a timeout drops into a random column that
is not full.

**Game view** (`match.game`):

```ts
type ConnectFourGame = {
  board: (1 | 2 | null)[][];            // [row][column] -> seat
  seats: Record<string, 1 | 2>;         // player id -> seat
  firstMover: string;
  turn: string | null;                  // null once the game is decided
  turnDeadline: number | null;          // epoch ms
  lastMove: {row: number; column: number; playerId: string} | null;
  winner: string | null;
  winningCells: [number, number][] | null; // [row, column], the whole run (4 or more)
  // players in the match only:
  isYourTurn?: boolean;
  legalMoves?: number[];                // open columns on your turn, else []
};
```

### 7.10 `penalty_kick`: Penalty Kick

A series game (7.7) with one shootout per match (`bestOf` does not apply; a shootout never
draws). **Settings** (defaults shown):

```json
{"kicksPerPlayer": 5, "keeperSpeed": "normal"}
```

| Setting | Values | Notes |
| --- | --- | --- |
| `kicksPerPlayer` | `3`, `5` | Regulation kicks for each player before sudden death. |
| `keeperSpeed` | `"easy"`, `"normal"`, `"hard"` | How fast the keeper patrols while the shooter aims. |

Positions are in the **goal plane**, seen from behind the shooter by everyone: `x` from 0
(left post) to 1 (right post), `y` from 0 (ground) to 1 (crossbar).

**Actions:**

| Action | Who | When |
| --- | --- | --- |
| `{"type": "shoot", "aim": {"x": number, "y": number}, "power": number}` | the shooter | `aiming` |
| `{"type": "dive", "x": number, "y": number}` | the keeper | `flight` |

`aim.x`/`aim.y` must be finite numbers in -0.5..1.5 and `power` in 0..1. A dive's `x`/`y` must
be finite numbers and are clamped to -0.1..1.1. The keeper's position is the point between
the hands; home is (0.5, 0.3).

| Error | When |
| --- | --- |
| `NOT_YOUR_TURN` | You are not in a live match. |
| `INVALID_ACTION` | Wrong action for your role; bad aim, power or dive numbers; a shot after the ball is kicked; a dive during `aiming`; shootout over. |

A dive that arrives after `arriveAt + graceMs` (server receive time), or any dive after the
first one, is **ignored** (the request is acknowledged, nothing changes).

**Rules**
- The game's first mover shoots first; shooter and keeper swap every kick.
- Each kick has three phases:
  1. `aiming`: the shooter has `PENALTY_AIM_MS` (12 s). On time out the server takes a mild
     shot inside the goal (power 0.5); this counts as a timeout (AFK, 7.7). The keeper
     player cannot act; the keeper patrols on `keeperPath`: from home, pause
     `PENALTY_KEEPER_PAUSE_MS[keeperSpeed]`, move in a straight line to a random point
     (x 0.2..0.8, y 0.3..0.36) at `PENALTY_KEEPER_SPEED[keeperSpeed]` goal widths per second,
     pause, and so on (easy 0.3 / 600 ms, normal 0.5 / 350 ms, hard 0.8 / 150 ms).
  2. `flight`: from the moment the shot is accepted, the ball flies for
     `PENALTY_FLIGHT_MS_MAX` (1.3 s, power 0) down to `PENALTY_FLIGHT_MS_MIN` (0.7 s, power 1),
     linear in power. The keeper stops where the patrol was when the shot was accepted
     (`keeperSpot`) and may dive from there until `arriveAt + PENALTY_DIVE_GRACE_MS` (250 ms).
  3. `result`: resolved at `arriveAt + grace`, shown for `PENALTY_RESULT_MS` (2.5 s); then the
     next kick starts, or the shootout ends.
- Resolution:
  - `power < PENALTY_POWER_FIZZLE` (0.15): `fizzled`, the ball stops short.
  - Otherwise the real aim is the aim plus gaussian wobble on each axis with
    sd = `PENALTY_WOBBLE_BASE` (0.03) + `PENALTY_WOBBLE_WILD` (0.14) × how far power exceeds
    `PENALTY_POWER_SWEET_MAX` (0.8), as a fraction of the rest of the range. `y` never goes
    below 0. The real aim is fixed when the ball is kicked.
  - Beyond an edge by more than `PENALTY_POST_MARGIN` (0.03): `wide` (x) or `over` (y);
    within the margin: `post`. These cannot be saved.
  - On target: `saved` when the ball (radius 8 scene units at the goal) touches the keeper's
    body, or, after a dive, lands within `PENALTY_SAVE_RADIUS` (0.14) + `PENALTY_SLOW_BONUS`
    (0.08) × (1 − power) goal widths of the dive point. Otherwise `goal`. Distances use the
    drawn goal's proportions (280 × 180 scene units). The body is the drawn keeper around the
    hands point (scene units, y down): head circle (0, −58) r 13, gloves (±28, 0) r 7, torso
    x −16..16 y −44..12, shorts and legs x −15..15 y 8..54, arms (±14, −36)–(±28, 0) r 4.
    Standing at `keeperSpot`, or diving: the hands at the dive point, the body leaning
    clamp((dive.x − keeperSpot.x) × 160, −80, 80) degrees clockwise around the hands.
  - Only `goal` scores.
- After `kicksPerPlayer` kicks each, the higher score wins. The shootout is decided as soon as
  one side cannot catch up; the winner is declared when that kick's `result` phase ends.
  Tied after regulation: sudden death, one kick each, until a pair of kicks leaves the scores
  different.

**Game view** (`match.game`). Public: nothing in it is secret once the ball is kicked. During
`aiming` it carries no aim at all; during `flight` it carries the real aim but never the
outcome. Use the push's `serverNow` with `launchAt`/`arriveAt` to animate the ball.

```ts
type Point = { x: number; y: number };
type PenaltyOutcome = 'goal' | 'saved' | 'wide' | 'over' | 'post' | 'fizzled';

type PenaltyKick = {
  kick: number;                         // 1-based
  shooter: string;
  keeper: string;
  to: Point;                            // the real aim
  power: number;                        // 0..1
  keeperSpot: Point;                    // where the keeper stood at the kick
  dive: Point | null;                   // null: the keeper did not dive
  outcome: PenaltyOutcome;
};

type PenaltyFlight = {
  launchAt: number;                     // epoch ms
  arriveAt: number;
  graceMs: number;                      // dives count until arriveAt + graceMs
  ball: { from: Point; to: Point; power: number };  // from: the spot, (0.5, 0)
  keeperSpot: Point;                    // where the keeper stood at the kick
  dive: (Point & { receivedAt: number }) | null;    // the accepted dive
};

type PenaltyGame = {
  kicksPerPlayer: number;
  keeperSpeed: 'easy' | 'normal' | 'hard';
  firstMover: string;
  phase: 'aiming' | 'flight' | 'result' | 'over';
  shooter: string | null;               // of the kick in play (or just taken); null once over
  keeper: string | null;
  kickNo: number;                       // 1-based, the kick in play (or just taken)
  round: number;                        // 1-based; a round is one kick each
  suddenDeath: boolean;
  scores: Record<string, number>;
  kicks: PenaltyKick[];                 // resolved kicks, in order
  lastKick: PenaltyKick | null;
  turnDeadline: number | null;          // aiming only: the shooter's deadline, epoch ms
  keeperPath: (Point & { at: number })[] | null;  // aiming only: patrol keyframes, epoch ms;
                                        // straight lines between them, the last one held
  flight: PenaltyFlight | null;         // flight and result
  outcome: PenaltyOutcome | null;       // result only
  resultUntil: number | null;           // result only: when the next kick (or the end) is due
  winner: string | null;
  // players in the match only:
  yourRole?: 'shooter' | 'keeper' | null;
};
```

**Events** (plus the series events, all tagged with `matchId`):
- `penalty_launch`: `{kick, shooter}` when the ball is kicked.
- `penalty_result`: `PenaltyKick & {scores}` when the kick resolves.

### 7.11 `checkers`: Checkers

A series game (7.7) with American rules. **Settings** (defaults shown):

```json
{"bestOf": 1, "flyingKings": false, "backwardCapture": false}
```

| Setting | Values | Notes |
| --- | --- | --- |
| `bestOf` | `1`, `3` | Games per match; first to the majority wins. |
| `flyingKings` | boolean | Kings move any distance diagonally and capture from a distance, landing on any empty square past the captured piece. |
| `backwardCapture` | boolean | Men may also capture backward. |

**Board:** 8×8, `[row, col]` with row 0 at the top. Only dark squares (`(row + col)` odd)
are used. Seat 1 (red, `a`) starts on rows 5–7 and moves up (toward row 0); seat 2 (blue,
`b`) starts on rows 0–2 and moves down. 12 pieces each.

**Action:** `{"type": "move", "from": [r, c], "to": [r, c]}`: one step or ONE capturing hop.

| Error | When |
| --- | --- |
| `NOT_YOUR_TURN` | It is your opponent's turn. |
| `INVALID_ACTION` | Not one of your `legalMoves` (including a non-capture while a capture exists, or another piece during a multi-jump); unknown `type`. |

**Rules**
- Men move one square diagonally forward; kings one square in any diagonal direction (any
  distance with `flyingKings`). A capture jumps one enemy piece onto the empty square behind
  it (any empty square past it for a flying king); the captured piece is removed at once.
- **Capturing is mandatory:** when any capture exists, only captures are legal.
- **Multi-jump:** after a capturing hop, if the same piece can capture again, the same player
  keeps the turn and only that piece may move, only by capturing (`forcedPiece`). The turn
  ends when that piece has no further capture.
- A man reaching the far row is crowned king and the turn ends at once, even if another
  capture would have been possible.
- A player with no pieces or no legal move on their turn loses. `CHECKERS_DRAW_PLIES` (80)
  plies in a row without a capture or a man move draw the game (`quietPlies` counts them;
  each hop is a ply).
- Each hop lasts up to `CHECKERS_TURN_MS` (45 s); the timer restarts after every hop. A
  timeout plays a random legal move (AFK rules in 7.7).

**Game view** (`match.game`; everything is public):

```ts
type CheckersPiece = {seat: 1 | 2; king: boolean};
type CheckersMove = {from: [number, number]; to: [number, number]; captures: [number, number][]};

type CheckersGame = {
  board: (CheckersPiece | null)[][];    // [row][col]
  seats: Record<string, 1 | 2>;         // player id -> seat
  firstMover: string;
  turn: string | null;                  // null once the game is decided
  turnDeadline: number | null;          // epoch ms
  forcedPiece: [number, number] | null; // the piece that must continue a multi-jump
  lastMove: (CheckersMove & {playerId: string; crowned: boolean}) | null;
  quietPlies: number;
  drawPlies: number;                    // CHECKERS_DRAW_PLIES
  flyingKings: boolean;
  backwardCapture: boolean;
  winner: string | null;
  draw: boolean;
  isYourTurn?: boolean;                 // players in the match only
  legalMoves?: CheckersMove[];          // only the player to move; mandatory capture and
                                        // multi-jump already applied
};
```

**Events:** the series events only (7.7).

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

### 8.8 Account recovery by SMS

An account can keep one confirmed phone number for resetting a forgotten password. Codes are
`PHONE_CODE_LENGTH` (6) digits, sent by SMS (Teleconic), valid `PHONE_CODE_TTL_MINUTES` (10),
`PHONE_CODE_MAX_TRIES` (5) tries; a number gets at most `PHONE_CODES_PER_HOUR` (3) codes. Numbers
are stored as digits with the country code; a leading 0 means `PHONE_DEFAULT_COUNTRY_CODE` (233).
Requests are rate limited per IP (`RATE_LIMITED`).

- `POST /api/me/phone` (Bearer) `{phone}` → `{sent: true, phone}` (masked, e.g. `"+233•••••0000"`).
  Texts a code; the number is saved only once confirmed. `PHONE_TAKEN` (409) if another account has it.
- `POST /api/me/phone/verify` (Bearer) `{code}` → `{phone}`; `INVALID_CODE` (400) when wrong or expired.
- `DELETE /api/me/phone` (Bearer) → `{phone: null}`.
- `GET /api/auth/me` gains `phone`: the masked confirmed number, or null.
- `POST /api/auth/password/forgot` `{login}` (username or phone number) → always `{sent: true}`;
  a code is texted only when the account exists and has a confirmed number.
- `POST /api/auth/password/reset` `{login, code, password}` → a new session `{token, profile,
  stats}`. `INVALID_CODE` (400) or `INVALID_INPUT` (password rules). Every access token issued
  before the reset stops working (HTTP and WebSocket); the player logs in again elsewhere. The
  code may also be the one texted after a staff-approved recovery request (below); its number
  then becomes the account's recovery number.
- `POST /api/auth/recovery/request` `{username, phone, answers: {nickname, joined?, friend?,
  games?, note?}}` → always `{received: true}`: for accounts without a recovery number. Staff
  compare the answers with the account at `/admin/recovery` (`GET /api/admin/recovery`,
  `POST /api/admin/recovery/<id>/approve|reject` `{note?}`, audit-logged). Approval texts a
  code valid `RECOVERY_CODE_HOURS` (24), `PHONE_CODE_MAX_TRIES` tries. A newer request replaces
  an open one. `INVALID_INPUT` for a missing username, phone or nickname.

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
| `in_game` | Seated in a room whose status is `"playing"` and still in the game (`inGame`), or in a solo room (16) in any state. |
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

### 9.6 People online (finding new friends)

A registered player can opt in to be listed: `PATCH /api/me/settings` `{discoverable: true}`
(`GET` returns `{presence, discoverable}`; default false, so nobody is listed without choosing
it). Request `friends:discover` `{}` (after `auth:hello`; else `UNAUTHORIZED`; rate limited like
game actions) → `{players: [{tag, nickname, avatar, color, status, relationship}]}`: up to
`DISCOVER_MAX` (30) listed players connected right now whose status is `online`, `in_lobby` or
`in_game`, newest connections first. Never the caller, their friends, busy or hidden players, or
anyone blocked either way. `relationship` is `none`, `requested` or `incoming`; a request is sent
the usual way (`POST /api/friends/requests` `{tag}`, with its limits).

## 10. Admin reports API (staff)

Part of the staff JSON API under `/api/admin/` used by the `/admin` dashboard. Same rules as the
rest of it: staff only (anonymous `401`, non-staff `403`, both with `loginUrl`), the Django admin
session cookie, CSRF token from `GET /api/admin/session` in `X-CSRFToken` on every POST, and
`X-Robots-Tag: noindex, nofollow`. The report endpoints also send `Cache-Control: no-store`.
Resolving and dismissing are written to the Django admin log (`LogEntry`), like disabling and
deleting accounts. Staff may see login usernames here; passwords, tokens and emails are never
included.

Staff log in on the dashboard itself: `POST /api/admin/login` with `{username, password}` (CSRF
token required) returns the same body as `GET /api/admin/session`, with a fresh `csrfToken`.
Wrong credentials or a non-staff account give `400 INVALID_LOGIN`; after `ADMIN_LOGIN_MAX_FAILS`
failures per IP + username, `429 LOCKED` for `ADMIN_LOGIN_LOCK_MINUTES`. `POST /api/admin/logout`
ends the session. The dashboard never redirects to the Django admin pages.

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

## 12. Registered-only games

`REGISTERED_ONLY_GAMES` in `shared/constants.json` (today `tic_tac_toe`, `connect_four`,
`checkers`, `penalty_kick`) lists games only registered accounts may play. Client and server
both read that list; there is no other copy. **Any future registered-only game must be added
to it.** The other games stay open to everyone.

- **Selecting:** `room:selectGame` with one of them fails with `REGISTERED_ONLY` unless the host
  is a registered account. Guests may still join a lobby that has one selected.
- **Starting:** `game:start` fails with `REGISTERED_ONLY` if the host is a guest. Seated guests
  are left out (`inGame: false` from the start, as for locked guests in 11). If fewer than the
  game's minimum players remain, the start fails with `REGISTERED_ONLY`,
  `data: {nicknames: string[]}` (the guests), and nothing changes. The guest free-games counter
  (11) is never touched by these games.
- **While it runs:** guests receive no `game:view` for it, and any `game:action` from a guest
  (including the spectator `watch`) fails with `REGISTERED_ONLY`.
- **`room:state` for guests:** while a registered-only game is selected (or running),
  `selectedGame` and `settings` are `null` in the copy a guest receives (also in `room:create` /
  `room:join` acks). Every copy marks guests with `Player.registeredOnlyBlocked: true`; blocked
  guests are left out of `readyCheck`.
- **Host transfer:** if host passes to a guest while one is selected, the selection is cleared
  and everyone gets `room:event` `game_unselected` (`data: {reason: "registered_only"}`).

## 13. Turning games off (staff)

Staff can turn any registered game off, and back on, from the Games page of the `/admin`
dashboard. A game that is off is hidden from players and cannot be played; its past sessions,
stats and leaderboards stay. The switch is stored in `analytics.GameAvailability` (no row means
on), so it survives restarts, and the server keeps the off set in memory (one process).

- **Rooms:** `RoomPublic.disabledGames` lists the off games; the game picker leaves them out.
  `room:selectGame` and `game:start` with one of them fail with `GAME_DISABLED`.
- **When a game is turned off:** every lobby that has it selected loses the selection (settings
  reset to `{}`, ready flags cleared), the room gets `room:event` `game_unselected`
  (`data: {reason: "disabled"}`), and every room receives a fresh `room:state`. A game already
  running, and its results screen, are left alone; `game:playAgain` then clears the selection
  the same way.
- **Admin API** (same rules as 10):
  - `GET /api/admin/games`: each row also has `enabled: boolean` and `known: boolean` (false
    for ids only found in old sessions; those have no switch). The response has
    `permissions: {toggle: boolean}`.
  - `POST /api/admin/games/<gameId>/disable` and `.../enable`: `{ok: true, enabled}`. Needs the
    `analytics.change_gameavailability` permission (superusers have it), else `403`; an unknown
    game or action is `404`. A real change is written to the Django admin log
    (`"Turned <name> off"` / `"... on"`); repeating the current state changes nothing.

## 14. Nemesis wallet (HTTP only)

Nemesis is the opt-in real-money wallet for registered players. **None of its data (balance,
status, limits, anything) is ever sent over the WebSocket**: not in `room:state`, not in any
push, not in another player's payload. Everything goes through plain HTTP with the account's
Bearer token, and every response is `Cache-Control: no-store`.

All amounts are integers in pesewas (`minorUnit` 100, `currency` "GHS"). The server computes
every balance, limit and eligibility check; the client only displays them.

`NEMESIS_ENABLED` (environment, default off) is the master switch. While it is off only
`GET /api/nemesis/status` answers (`{enabled: false}`); every other route below is `404`.

- `GET /api/nemesis/status` → `{enabled, active, rulesVersion, eligibility: {accountAgeOk,
  hoursLeft, gamesPlayed, gamesNeeded, idState}, idState, attemptsLeft, rejectionReason,
  retentionDays, excluded}`. `idState` is `none | pending | approved | rejected |
  rejected_final`.
- `POST /api/nemesis/id` (multipart: `idType`, `fullName`, `idNumber`, `dob` YYYY-MM-DD,
  `front`, optional `back`) → `201` with the status. Photos must be JPEG or PNG (checked by their
  bytes) of at most `ID_MAX_BYTES`; at most `ID_MAX_ATTEMPTS` submissions per account and none
  while one is pending (`INVALID_STATE`); 5 uploads per hour (`RATE_LIMITED`). Only a keyed hash
  and the last 4 characters of the ID number are kept. A date of birth under
  `NEMESIS_MIN_AGE_YEARS` is `rejected_final` at once (no photos kept). Photos are stored
  privately, reachable only by staff, and deleted `ID_IMAGE_RETENTION_DAYS` after the decision
  (at once if the account is deleted).
- `POST /api/nemesis/activate {confirmAge: true, acceptRules: true, rulesVersion}` → status.
  Errors: `ALREADY_ACTIVE`, `EXCLUDED`, `ID_REQUIRED`, `NOT_ELIGIBLE` (with `eligibility`),
  `INVALID_INPUT` (missing confirmation or old `rulesVersion`). No credit of any kind is given.
- `POST /api/nemesis/deactivate` → status. Immediate; `NOT_ACTIVE` if off, `DEPOSIT_OPEN` while a
  deposit request is open. Balance, history and withdrawals stay available while off.
- `GET /api/wallet` → `{currency, minorUnit, balance, held, limits: {platform: {depositMin,
  depositMax, depositDaily, deposit30d, withdrawMin, withdrawDailyCap}, player: {depositDaily,
  deposit30d}, pendingRaise: {depositDailyLimit, deposit30dLimit, effectiveAt} | null},
  exclusion: {active, permanent, until}, payout: {method, network, number (masked), accountName,
  effectiveAt, effective} | null, flags: {depositsEnabled, withdrawalsEnabled, stakingEnabled}}`.
  `balance` is available; `held` is waiting on withdrawals.
- `GET /api/wallet/entries?cursor=<id>` → `{entries: [{id, kind, amount (signed), balanceAfter,
  account: "available" | "held", createdAt}], nextCursor}`, newest first, `WALLET_PAGE_SIZE`
  per page. Kinds: `deposit`, `withdrawal_hold`, `withdrawal_paid`, `withdrawal_refund`,
  `adjustment`.

**Deposits, withdrawals, limits, breaks.** Every POST accepts an `Idempotency-Key` header: a
repeated key (per account and route, 24 h) returns the first successful response unchanged.
Deposits, payment details and deposit submits need an **active** profile (`NOT_ACTIVE`);
withdrawals, the payout destination, limits and breaks also work while off or on a break.

- `GET /api/wallet/payment-details` → `{method, network, number, accountName}` (where to pay).
- `POST /api/wallet/deposits {amount}` → `201` deposit `{id, reference ("NEM-XXXXXX"), amount,
  amountReceived, status, paymentDetails (snapshot), paymentRef, senderNumber, createdAt,
  expiresAt, submittedAt, rejectReason}`. Errors: `EXCLUDED`, `FEATURE_DISABLED`, `DEPOSIT_OPEN`
  (with `id`), `LIMIT_REACHED` (with `remaining`), `INVALID_INPUT` (outside
  `DEPOSIT_MIN..DEPOSIT_MAX`). The player pays outside the app with the reference in the
  payment note. Unpaid requests expire after `DEPOSIT_REQUEST_TTL_MIN`.
- `POST /api/wallet/deposits/<id>/submit {paymentRef, senderNumber}` → deposit, now
  `pending_review`. `paymentRef` is uppercased with spaces and punctuation removed; one already
  pending or approved is `DUPLICATE_REFERENCE`. Sending the same data again returns the same
  result.
- `POST /api/wallet/deposits/<id>/cancel` (only `awaiting_payment`); `GET /api/wallet/deposits`
  → `{deposits: [...], open: deposit | null}` (resume an open request after a refresh).
- `POST /api/wallet/payout-destination {method: "mobile_money" | "bank", network (one of
  PAYMENT_NETWORKS), number, accountName, password}` → `{payout}` (number masked). The first
  destination is effective at once; a change waits `PAYOUT_CHANGE_DELAY_HOURS`.
- `POST /api/wallet/withdrawals {amount}` → `201` withdrawal `{id, amount, status, createdAt,
  eligibleAt, payout (masked), payoutReference (when paid), paidAt, rejectReason}`. The amount
  moves to `held` at once. Errors: `FEATURE_DISABLED`, `PAYOUT_NOT_SET`, `PAYOUT_PENDING`,
  `WITHDRAWAL_PENDING`, `LIMIT_REACHED` (`WITHDRAW_DAILY_CAP`, with `remaining`),
  `INSUFFICIENT_FUNDS`, `INVALID_INPUT` (below `WITHDRAW_MIN`). Staff pay no earlier than
  `eligibleAt` (`WITHDRAW_FIRST_DELAY_HOURS` after the account's first request).
- `POST /api/wallet/withdrawals/<id>/cancel` (only `pending_review`; funds return);
  `GET /api/wallet/withdrawals` → `{withdrawals: [...]}`.
- `PUT /api/wallet/limits {depositDailyLimit, deposit30dLimit}` → the `limits` object of
  `GET /api/wallet`. Lowering applies at once; raising waits `LIMIT_RAISE_DELAY_HOURS`
  (`pendingRaise`). Never above the platform maximums.
- `POST /api/wallet/exclude {days: 7 | 30 | "permanent"}` → `{exclusion}`. Starts at once; a
  break can be lengthened, never shortened; a permanent one only staff can lift. While on a
  break: no deposits and no turning Nemesis on; withdrawals still work.

**Client.** Only `/profile` shows Nemesis (a "Nemesis" section for registered players, rendered
only when `status.enabled` is true); nothing else in the app mentions it. The client formats
amounts with `Intl.NumberFormat` in the server's currency and never computes a balance, limit or
eligibility itself.

**Ledger.** Double-entry and zero-sum (`nemesis/ledger.py` is the only code that changes a
balance; entries are never edited or deleted). `python manage.py check_ledger` verifies that all
entries sum to zero and every cached balance equals its entries; the daily background task runs
the same check and logs an ERROR on a mismatch.

## 15. Nemesis staff tools (admin API)

Same rules as section 10 (staff session, `X-CSRFToken` on POST/PUT, `{"error": {code,
message}}`), plus: every response is `Cache-Control: no-store`, every action is written to the
Django admin log, and amounts are integer pesewas computed by the server.

**Two-factor (RFC 6238 TOTP: SHA-1, 30-second steps, 6 digits, ±1 step).**
- `POST /api/admin/2fa/setup` → `{secret, otpauthUri}` (while not enrolled; again restarts).
- `POST /api/admin/2fa/confirm {code}` → `{backupCodes: [10]}`, shown once (only hashes are
  stored). Enrols and marks the session as two-factor.
- `POST /api/admin/login {username, password, code}`: once enrolled the code (or an unused backup
  code, consumed) is required: `CODE_REQUIRED` / `INVALID_CODE`, both with `needsCode: true`.
  Wrong codes count towards the login lockout (`LOCKED`). A code is never accepted twice.
- `POST /api/admin/2fa/step-up {code}` → `{ok}`; valid for `STEP_UP_MINUTES`.
- `GET /api/admin/session` adds `money: {enrolled, verified, permissions, pending: {deposits,
  withdrawals, ids, adjustments} | null}`.

Every money and ID endpoint below needs a session that passed two-factor
(`TWO_FACTOR_REQUIRED` otherwise; a password-only session such as the Django admin login never
counts), the named permission (`FORBIDDEN`), and, where marked **step-up**, a step-up within
`STEP_UP_MINUTES` (`STEP_UP_REQUIRED`: ask for a code, call step-up, retry). Permissions are
Django permissions given through groups: `nemesis.review_ids`, `review_deposits`,
`review_withdrawals`, `adjust_balances`, `edit_merchant`, `edit_flags` (superusers hold all).
Staff can never act on their own account's requests (`FORBIDDEN`).

**Dual approval.** With `DUAL_APPROVAL_ENABLED`, deposits and withdrawals of at least
`DUAL_APPROVAL_THRESHOLD`, and every adjustment, merchant change and flag change, take effect
only when a second, different staff member approves (`firstApprovedBy` / `pending` show the
first step). Off, step-up alone is enough.

- **IDs** (`review_ids`): `GET /api/admin/ids?status=pending|approved|rejected|rejected_final|all`
  → `{ids: [{id, user: {userId, nickname, tag}, idType, fullName, last4, status, attemptNumber,
  flaggedDuplicate, createdAt, ageSeconds, reviewedBy, reviewedAt, rejectionReason, hasFront,
  hasBack, imagesDeletedAt}]}`; `GET /api/admin/ids/<id>` adds `submittedDob`.
  `GET /api/admin/ids/<id>/image/front|back` (**step-up**) streams the photo (audit-logged);
  this is the only way to see one. `POST .../approve {dob}` (**step-up**; the reviewer re-enters
  the date of birth; under age → `rejected_final`; ID number approved elsewhere →
  `ID_ALREADY_USED` and the submission is flagged). `POST .../reject {reason}` (**step-up**;
  the last attempt becomes `rejected_final`).
- **Deposits** (`review_deposits`): `GET /api/admin/money/deposits?status=` (pending first) →
  `{deposits: [{id, user, reference, amountRequested, amountReceived, status, paymentRef,
  senderNumber, merchantSnapshot, createdAt, submittedAt, ageSeconds, firstApprovedBy,
  reviewedBy, reviewedAt, rejectReason, note, own}], dualApproval}`; `GET .../<id>`.
  `POST .../<id>/approve {receivedAmount, verifiedInAccount: true, note?}` (**step-up**): the
  reviewer confirms they saw the payment in the receiving account; a different amount needs a
  `note` and only `receivedAmount` is credited; a second approval is `INVALID_STATE`.
  `POST .../<id>/reject {reason}` (**step-up**).
- **Withdrawals** (`review_withdrawals`): `GET /api/admin/money/withdrawals?status=` →
  `{withdrawals: [{id, user, idName, amount, status, payoutSnapshot (full number), createdAt,
  eligibleAt, eligible, ...}]}`; `GET .../<id>`. `POST .../<id>/approve` (**step-up**, only once
  `eligibleAt` has passed), `POST .../<id>/mark-paid {payoutReference}` (**step-up**, after paying
  by hand; the held amount leaves), `POST .../<id>/reject {reason}` (**step-up**; funds return).
- **Adjustments** (`adjust_balances`, **step-up**): `GET /api/admin/money/adjustments`;
  `POST /api/admin/money/adjustments/propose {userId, amount (signed), reason}`;
  `POST .../<id>/approve|reject`. Corrections post new entries between the player's account and
  external (never escrow) and never edit existing ones.
- **Merchant details**: `GET /api/admin/money/merchant` → `{active, versions, dualApproval}`;
  `PUT` the same path `{method, network, number, accountName}` (`edit_merchant`, **step-up**)
  creates a new version; `POST .../merchant/<id>/approve` (second approver). Open deposit requests
  keep the details they were shown.
- **Flags**: `GET /api/admin/money/flags` → `{flags, pending, updatedAt, dualApproval}`;
  `POST` the same path `{field: depositsEnabled | withdrawalsEnabled | stakingEnabled, value}`
  (`edit_flags`, **step-up**); `POST /api/admin/money/flags/approve` (second approver).
- **Reconciliation** (`review_deposits`): `GET /api/admin/money/reconcile` → `{latest, history,
  ledger}`; `POST {reportedBalance}` stores a report (`ok` is false when the real balance is
  below the ledger liabilities).
- `GET /api/admin/money/overview?range=` → `{liabilities, depositsTotal, withdrawalsTotal,
  pending, latestReport, ledgerOk, warnings: ["report_stale" | "report_short" |
  "ledger_mismatch"], lastMerchantChange, flags, dualApproval}`.
- `GET /api/admin/money/users/<id>` → `{verification (review_ids), wallet: {balance, held,
  active, exclusion} (any money permission), canRemoveExclusion}`;
  `POST .../remove-exclusion` (`adjust_balances`, **step-up**) lifts a permanent break.
- `GET /api/admin/money/audit` → the latest 100 admin-log rows about Nemesis records.

**Account deletion** (by the player or staff) is refused with `HAS_FUNDS` while the account has a
nonzero balance, held funds, or an open deposit or withdrawal.

## 16. Solo games

A registered player plays alone against a bot in a private **solo room**: one player seat and
one bot seat. Today `tic_tac_toe`, `connect_four`, `dots_and_boxes` and `penalty_kick`. Solo games are never staked and never
count toward the scoreboard, `PlayerStats`, analytics sessions, recent players, the guest
free-games counter (11) or placement points; only the player's own solo record changes.

**Requests**

- `solo:start` `{gameId, variant?: {difficulty?, size?}}` → ack `{code, roomToken, playerId, room}`.
  `difficulty` is one of `SOLO_DIFFICULTIES` (default `"medium"`); `size` only for
  `dots_and_boxes`: 4, 5 or 6 (default 5). Guests (including an invalid
  `authToken`): `REGISTERED_ONLY`. Another `gameId` or an unknown option: `INVALID_ACTION`; a game
  staff turned off: `GAME_DISABLED`. Fails with `INVALID_ACTION` while this connection holds a
  seat in a normal room. The account's previous solo room, if any, is closed first (its sockets
  get `NOT_IN_ROOM`; nothing is recorded). The connection takes the player seat (seat 1) as with
  `room:create`, and the game starts at once: no lobby or ready check. The first mover is random.
- `solo:again` `{}` (the owner, after the game finished) → `{}`: a new game, same variant; the
  first mover alternates. While a game runs: `GAME_IN_PROGRESS`.
- `solo:quit` `{}` → `{}`: closes the room. Nothing is recorded. `room:leave` in a solo room
  does the same.
- In a solo room every other room request (`room:react`, `room:ready`, `game:quit`,
  `invite:send`, by-player actions, ...) fails with `INVALID_ACTION`.

**Privacy.** `room:peek` reports a solo room as `exists: false`; `room:join` returns
`ROOM_NOT_FOUND` to everyone except the owner reclaiming the seat (by `roomToken` or account,
4.2). It is never invited to, spectated or listed. Friends see the owner as `in_game` (9.2).

**The bot** is the second player in `room:state`: `bot: true`, `type: "bot"`, nickname `"Bot"`,
`avatar: null`; it has no account, tag or presence. It moves through the same validation and
timers as a player, after a think time of `BOT_THINK_MS_MIN`..`BOT_THINK_MS_MAX` (never more
than half the time left on the turn), and reads only what a player in its seat could see.

**Dots and Boxes** (7.4) runs unchanged for two, with its own `game:view` shape; the first mover
is random, then alternates with `solo:again`. Closing a box keeps the turn, so the bot may act
several times in a row (after `BOT_CONTINUE_MS_MIN`..`BOT_CONTINUE_MS_MAX` each). Equal boxes is a
draw. **Penalty Kick** (7.10) is 5 kicks each plus sudden death (no draws), keeper speed
`normal`, with `diveGraceMs` = `SOLO_PENALTY_DIVE_GRACE_MS`. The bot shoots after
`BOT_PENALTY_SHOOT_MS_MIN`..`BOT_PENALTY_SHOOT_MS_MAX` and, as keeper, dives after a reaction time
from what a keeper sees at launch (the ball's real aim); a dive after the grace is ignored.

**The other games** use the game's rules and `game:view` shape (7.7 to 7.9) as one best-of-1 match
(`bestOf: 1`, match id `"solo"`): a draw ends the game as a draw (no replay or coin flip). Turn
timers apply as in 7.7 (a timed-out move is random; `MATCH_AFK_TIMEOUTS_TO_FORFEIT` in a row
lose). There is no offline forfeit: a solo room with no connected socket closes after
`SOLO_IDLE_TTL_MS` and records nothing. When the game ends the room status becomes `finished`
(no `gameOver` event, no scoreboard change) and every solo `game:view` carries:

```ts
type SoloResult = {
  outcome: 'win' | 'lose' | 'draw';
  record: { plays: number; wins: number; losses: number; draws: number } | null;  // null if saving failed
};
// game:view data.view.soloResult: SoloResult | null (null until the game ends)
```

`record` is the player's updated record for this game and difficulty.

**HTTP.** `GET /api/solo/records` (Bearer, `Cache-Control: no-store`) →
`[{gameId, variant, plays, wins, losses, draws, bestScore}]` for the signed-in account, by game
then variant. For bot games `variant` is the difficulty (`"<difficulty>:<size>x<size>"` for Dots
and Boxes, e.g. `"hard:5x5"`); `bestScore` is for future challenge
games (0 here). Errors as in 8.5.

### 16.1 Solo challenges

A challenge has no bot: one player seat, one run, a personal best to beat. `solo:start` takes:

| `gameId` | `variant` | SoloRecord `variant` | Running game id (`game:view` `gameId`) |
| --- | --- | --- | --- |
| `guess_race` | `{content: "scramble" \| "emoji" \| "mixed"}` (default mixed) | the content type | `solo_guess_run` |
| `name_it` | `{topic: <topic id> \| "random"}` (default random) | the topic played | `solo_name_it` |
| `hangman` | `{}` | `"classic"` | `solo_hangman` |

`RoomPublic.selectedGame` is the `gameId`; `soloVariant` is the variant sent (with defaults).
Topic ids and names are `SOLO_NAMEIT_TOPICS` in `shared/constants.json`. `solo:again` starts a new
run with the same variant; `solo:quit` records nothing. Actions reuse the multiplayer names:

- `guess_race`: `{type: "guess", text}` (1..`GUESS_TEXT_MAX` chars) and `{type: "skip"}`.
- `name_it`: `{type: "submitAnswer", text}` (1..40 chars).
- `hangman`: `{type: "guessLetter", letter}` (one letter a-z; a repeat is `INVALID_ACTION`).

**Guess Race "Beat the clock"** (`solo_guess_run`). One clock of `SOLO_GUESS_RUN_MS`. Puzzles one
at a time (mixed alternates scramble and emoji), easy first and one level harder every
`SOLO_LEVEL_EVERY` solves; none repeats in a run. A correct guess (multiplayer checking, any
listed anagram) scores `max(SOLO_GUESS_POINTS_MIN, SOLO_GUESS_POINTS_MAX -
SOLO_GUESS_POINTS_PER_SECOND x whole seconds on the puzzle)`; wrong guesses cost nothing. `skip`
costs `SOLO_GUESS_SKIP_PENALTY_MS` of run time; a puzzle unsolved after `SOLO_GUESS_PUZZLE_MS` is
skipped for free. Clues at `GUESS_HINT1_MS` and `GUESS_HINT2_MS` as in 7.2. The run ends when the
clock reaches zero. View:

```ts
type GuessRunView = {
  phase: 'playing' | 'done'; content: 'scramble' | 'emoji' | 'mixed'; kind: 'scramble' | 'emoji';
  prompt: string | null; hints: { type: 'category' | 'length' | 'firstLetter'; value: string | number }[];
  score: number; solved: number; skipped: number; level: number;   // level 1..3
  runEndsAt: number; puzzleStartedAt: number; puzzleEndsAt: number;
  lastResult: { correct: boolean; points: number; answerIfSkipped: string | null } | null;
  // answerIfSkipped: the skipped puzzle's answer, for SOLO_RESULT_MS. Never the current answer.
};
```

**Name It "Streak"** (`solo_name_it`). One answer at a time, `NAMEIT_TURN_MS` each. A listed answer
(name or alias; case, spaces, punctuation and accents ignored; no fuzzy matching) adds 1; a wrong
or unlisted answer, a repeat (any name of an entry already given) or a timeout is a strike, and
the timer restarts. `SOLO_NAMEIT_STRIKES` strikes end the run; naming every entry ends it with
`detail.completed: true`. View: `{phase, topic: {id, name, emoji}, streak, strikes, maxStrikes,
accepted: string[] (newest first), turnEndsAt, lastResult: {kind: "correct" | "wrong" | "repeat" |
"timeout"} | null, completed}`. The unused entries are never sent.

**Hangman "Word streak"** (`solo_hangman`). Words from `words.json` (5..9 letters a-z) by level as
above, no repeats. `HANGMAN_MAX_WRONG` wrong letters lose the word: a strike, and the word is shown
for `SOLO_HANGMAN_RESULT_MS` (phase `lost`) before the next. A solved word adds 1 and the next starts
at once. `SOLO_HANGMAN_STRIKES` strikes end the run. No time limit. View: `{phase: "guessing" |
"lost" | "done", mask: (string | null)[], guessed: {correct, wrong}, wrongCount, maxWrong, strikes,
maxStrikes, solved, level, wordNumber, revealedWord: string | null (only once lost), revealUntil}`.

**Finishing a run.** The SoloRecord gets `plays + 1` and `best_score = max(best, score)` (wins,
losses and draws stay 0); events `solo_started` / `solo_finished` carry `{game_id, variant, score,
duration}`. Every view then carries:

```ts
type ChallengeResult = {
  outcome: 'run_over'; score: number;
  detail: { solved, skipped, level } | { topic, strikes, completed } | { strikes, lastWord };
  best: number | null; isNewBest: boolean;
  record: { plays: number; bestScore: number } | null;   // null if saving failed
};
```

## 17. Brag coins (play money)

Brag coins are play money for registered accounts: they can never be bought, cashed out or sent
between players, and they have nothing to do with the Nemesis wallet (14). Every account gets
`BRAG_STARTER` (100) once, the first time its wallet is read or credited.

**Earning.** Beating a solo bot (16) on **Hard** pays `BRAG_HARD_REWARDS` (tic-tac-toe 100, Connect
Four 60, Penalty Kick 50, Dots and Boxes 40 / 70 / 100 on 4x4 / 5x5 / 6x6), at most `BRAG_WIN_CAP`
(100) per win and `BRAG_DAILY_CAP` (150) per day from bots (server midnight). Easy, Medium, draws
and challenges pay nothing. The Hard tic-tac-toe bot slips on its second move with probability
`BOT_TTT_HARD_SLIP` (1 in 8), so it can be beaten. A solo `soloResult` gains
`brag: {awarded, balance, dailyLeft, dailyCap} | null` (null unless a Hard win, or if saving failed;
`awarded: 0` once the daily cap is reached).

**HTTP.** `GET /api/brag` (Bearer, no-store) → `{balance, earnedToday, dailyCap, rewards,
history: [{amount, balanceAfter, kind, gameId, at}]}` (the 20 latest; kinds `starter`, `bot_win`,
`stake`, `pot_win`, `stake_refund`).

**Stakes (games between friends, any game and any number of players).**

- `room:setStake` `{amount}` (host, lobby) → `{}`: `amount` is 0 (no stake) or one of
  `BRAG_STAKES` (10, 25, 50, 100). The host must be registered and able to pay; the host is in,
  every other choice resets (with the ready flags), and everyone gets `room:event`
  `stake_changed` `{amount}`.
- `room:stakeChoice` `{join: boolean}` (registered players, lobby, a stake is set) → `{}`.
  Joining needs the coins: else `NOT_ENOUGH_BRAG` `data: {balance, stake}`. Guests:
  `REGISTERED_ONLY`.
- `game:start` with a stake: more than half of the seated players (guests count) must have
  joined, and at least the game's minimum: else `STAKE_NOT_AGREED` `data: {joined, needed}` (the
  host can lower or remove the stake). Players who did not join sit the game out (`inGame:
  false`, like 11). Each joiner's stake is taken then; anyone who can no longer pay sits out too
  (if too few remain, every stake is returned and the start fails with `NOT_ENOUGH_BRAG`).
- End: placement 1 takes the pot (`stake x players`, minus `BRAG_POT_FEE_PERCENT`, 0 today); a
  tie for first splits it; a tie of everyone, a game the host ends, or a room that closes mid-game
  returns every stake. Forfeiting players rank last (they lose their stake).
- `RoomPublic` gains `stake` (0 = none), `staked` (player ids in the pot of the running game),
  `pot`, and `stakeResult: {pot, refunded, winners, each} | null` (the last staked game, cleared
  by `game:playAgain`); `Player` gains `stakeChoice: "in" | "out" | null`.

