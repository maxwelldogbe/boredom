# Boredom WebSocket Protocol

> **Status: DRAFT (phase B0).** The envelope, event names, error codes and room types below are
> fixed. Sections marked **(B1)** or **(B2–B7)** are filled in as those phases land. This file is
> kept in sync with the code; if they ever disagree, report it.

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
| `room:state` | `data: RoomPublic` | After every room change, to everyone in the room. |
| `game:view` | `data: {gameId, view}` | After every game change, to each player separately (personalized). |
| `game:event` | `data: {kind, data}` | Transient moments: reveal, round over, elimination, challenge opened. |
| `error` | `data: {code, message}` | A problem not tied to a request, e.g. `BAD_MESSAGE` when the frame has no usable `id`. |

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
| `INVALID_ACTION` | Invalid payload, profile, settings, or game move. |
| `GAME_IN_PROGRESS` | Joining a room mid-game without a valid `roomToken` for a seat. |
| `RATE_LIMITED` | More than `ACTION_RATE_LIMIT_PER_SEC` (5) game actions per second on this connection. |
| `NOT_IN_ROOM` | Request needs a room but this connection has not joined one. |
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

### 4.2 `room:join`

Payload: `{ "code": "ABCD", "profile": Profile, "roomToken"?: string }`

- `code` is case-insensitive (uppercased by the server).
- With a `roomToken` matching a seated player: reclaims that seat (same `playerId`), marks it online.
- Without one: takes a new seat. Rejected with `GAME_IN_PROGRESS` unless the room status is `lobby`.

Ack data: same shape as `room:create`.

Errors: `ROOM_NOT_FOUND`, `ROOM_FULL`, `GAME_IN_PROGRESS`, `INVALID_ACTION` (bad profile).

### 4.3 `room:peek`

Payload: `{ "code": "ABCD" }`. Works without being in a room. Never fails for a missing room.

Ack data:

```json
{"exists": true, "hostNickname": "Sam", "playerCount": 3, "status": "lobby"}
```

For an unknown code: `{"exists": false, "hostNickname": null, "playerCount": 0, "status": null}`.

### 4.4 `room:leave`

Payload: `{}`. Leaves the current room. Ack data: `{}`. Errors: `NOT_IN_ROOM`.
Mid-game leave behaviour: **(B1)**.

### 4.5 `room:selectGame` (host only)

Payload: `{ "gameId": GameId, "settings": object }`. Settings are validated by the game module and
completed with defaults; the stored result appears in `RoomPublic.settings`.
Ack data: `{}`. Errors: `NOT_IN_ROOM`, `NOT_HOST`, `INVALID_ACTION`, `GAME_IN_PROGRESS`.

### 4.6 `game:start` (host only)

Payload: `{}`. Requires a selected game and a player count within its min/max.
Ack data: `{}`. Errors: `NOT_IN_ROOM`, `NOT_HOST`, `INVALID_ACTION`, `GAME_IN_PROGRESS`.

### 4.7 `game:action`

Payload: `{ "type": string, ...actionFields }`. Action types are per game (section 7).

Server checks in this order: in a room (`NOT_IN_ROOM`), room status `playing` (`INVALID_ACTION`),
rate limit (`RATE_LIMITED`), then the game module (`NOT_YOUR_TURN` / `INVALID_ACTION`).
On failure nothing changes. On success every player receives a fresh `game:view`.
Ack data: `{}`.

### 4.8 `game:playAgain` (host only)

Payload: `{}`. Returns the room to `lobby`, keeping the selected game, settings and scoreboard.
Ack data: `{}`. Errors: `NOT_IN_ROOM`, `NOT_HOST`, `INVALID_ACTION`.

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
  scoreboard: Record<string, number>;   // playerId -> session points
};

type GameResult = { playerId: string; placement: number; points: number };
```

Constants (`shared/constants.json`) are shared by client and server.

## 6. Room lifecycle **(B1)**

To be completed in B1: status transitions, host transfer, disconnect/reconnect, scoreboard
updates, game-over event, idle cleanup.

## 7. Games **(B2–B7)**

Each game's settings, actions, view and events are documented here as it is built.

| gameId | Phase |
| --- | --- |
| `rps` | B2 |
| `guess_race` | B3 |
| `hangman` | B4 |
| `dots_and_boxes` | B5 |
| `liars_dice` | B6 |
| `name_it` | B7 |
