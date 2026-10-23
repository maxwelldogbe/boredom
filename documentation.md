Party Pack: Project Documentation
A lightweight multiplayer web game collection for friends and family. Familiar games, made digital, playable on phones with a room code.

Status: Design phase | Version: 0.1

1. Overview
1.1 Vision
One app, many quick games. A friend creates a room, shares a 4-letter code, everyone joins on their phone, and the host picks a game. No accounts, no downloads, no database.

1.2 Goals
Existing, easy-to-learn games only. Nothing invented.
Light backend: in-memory state, small server.
Phone-first, playable in the same room or over a call.
One shared foundation so adding a new game is cheap.
Visuals only where a game needs them (emoji, CSS, inline SVG).
1.3 Non-goals (v1)
User accounts, profiles, or avatars uploads
Persistent history, leaderboards across sessions
Matchmaking with strangers
Native mobile apps
In-app voice or video chat
1.4 Assumptions
Group size is typically 2 to 10 friends.
Players trust each other; anti-cheat is limited to keeping hidden info server-side.
Free hosting tiers are acceptable. A cold start delay on the server is tolerable.
2. Game Lineup
#	Game	Players	Type	Complexity
1	Rock-Paper-Scissors	2+	Simultaneous pick	Lowest
2	Word Scramble	2-10	Race to guess	Low
3	Emoji Guess	2-10	Race to guess	Low
4	Hangman Duel	2+	Hidden word	Low
5	Dots and Boxes	2-4	Turn-based board	Low-medium
6	Liar's Dice	2-6	Hidden info, elimination	Medium
7	Name It Survival	3-10	Timed turns, voting, elimination	Medium
Games 2 and 3 share one "Guess Race" module with different content.

3. Architecture
3.1 High-level
 Phone (React) <--WebSocket (Socket.IO)--> Node server (in-memory rooms)
 Phone (React) <------------------------->        |
 Phone (React) <------------------------->   game modules
Server-authoritative: the server owns all game state. Clients send actions and receive views.
Hidden information stays on the server. The server sends each player only what they are allowed to see (their own dice, the masked hangman word).
No database. Rooms live in a Map in memory and are deleted after inactivity.
3.2 Tech stack
Layer	Choice	Reason
Frontend	React + Vite	Fast, simple, mobile friendly
Styling	Plain CSS or Tailwind	Lightweight, one theme
Realtime	Socket.IO (client + server)	Rooms, reconnection built in
Backend	Node.js + Express + Socket.IO	Minimal
Language	TypeScript (recommended)	Shared types for events
Hosting	Vercel/Netlify (client), Render/Railway (server)	Free tiers
3.3 Why in-memory state
A party session lasts under an hour and nothing must survive a restart. In-memory keeps the code small and fast. The trade-off: a server restart ends all active rooms. Acceptable for v1.

4. Core Foundation
Built once, used by every game.

4.1 Room system
Room code: 4 uppercase letters (exclude confusing letters like O, I). Regenerate on collision.
Roles: one host (creator) and players. If the host leaves, host passes to the longest-connected player.
Room states: lobby → playing → between_rounds → finished.
Limits: max 10 players per room, nickname 1 to 12 characters, unique within the room.
Cleanup: delete a room when empty, or after 2 hours of inactivity.
4.2 Player identity and reconnection
On join, the server issues a random playerToken, stored in the browser's localStorage.
On reconnect (page refresh, phone sleep), the client sends the token and reclaims its seat.
A disconnected player is marked offline. Each game defines what happens next (skip turn, auto-forfeit after timeout).
4.3 Lobby
Shows the room code in large type, a copyable invite link (/join/ABCD), and the player list with ready status.
The host selects a game and settings, then presses Start.
Minimum players per game are enforced before Start is enabled.
4.4 Scoring
Each game reports results as { playerId, placement, points }.
The room keeps a session scoreboard across games, with the overall champion shown at the end.
Suggested points: 1st = 3, 2nd = 2, 3rd = 1, others = 0. Games with per-round scores (Guess Race) add those directly.
4.5 Game module interface
Every game implements the same contract, so the room code never contains game-specific logic.

interface GameModule<State, Action, View> {
  id: string;
  minPlayers: number;
  maxPlayers: number;
  settingsSchema?: object;

  init(players: Player[], settings: object): State;
  handleAction(state: State, playerId: string, action: Action): Result<State>;
  tick?(state: State, now: number): State;      // timers
  getView(state: State, playerId: string): View; // per-player, hides secrets
  isOver(state: State): boolean;
  getResults(state: State): GameResult[];
}
The server calls handleAction, validates the outcome, then broadcasts getView to each player individually.

5. Realtime Protocol
5.1 Client to server events
Event	Payload	Purpose
room:create	{ nickname }	Create room, become host
room:join	{ code, nickname, token? }	Join or rejoin
room:leave	none	Leave room
room:selectGame	{ gameId, settings }	Host only
game:start	none	Host only
game:action	{ type, ...data }	Any in-game action
game:playAgain	none	Host only, back to lobby
5.2 Server to client events
Event	Payload	Purpose
room:state	{ code, players, hostId, status, selectedGame, scoreboard }	Lobby/room sync
game:view	game-specific view	Per-player game snapshot
game:event	{ kind, data }	Transient things (a reveal, a buzzer)
error	{ code, message }	Rejected action
Pattern: after any state change the server sends a fresh full game:view to each player. Snapshots are small, and this avoids sync bugs from partial updates.

5.3 Error codes
ROOM_NOT_FOUND, ROOM_FULL, NAME_TAKEN, NOT_HOST, NOT_YOUR_TURN, INVALID_ACTION, GAME_IN_PROGRESS.

6. Game Specifications
6.1 Rock-Paper-Scissors
Players: 2 (duel) or 3+ (bracket). Format: best of 3 or 5 (setting).

Flow:

Both players pick secretly (✊ ✋ ✌️).
When both have picked (or the timer ends), the server reveals both choices at once.
Point to the winner; ties replay. First to majority wins the match.
Bracket mode: pair players randomly, winners advance, odd player gets a bye.
State: { round, picks: {playerId: choice|null}, scores, phase }. Hidden info: a player's pick is not sent to the opponent until reveal. Views only say hasPicked: true/false. Edge cases: a player who does not pick before the timer (10s) loses the round; disconnect for 30s forfeits.

6.2 Guess Race: Word Scramble and Emoji Guess
Players: 2 to 10. One module, two content types.

Flow:
h

Server selects a prompt and sets a timer (default 30s).
All players type guesses simultaneously. Wrong guesses are allowed, unlimited.
First correct guess wins the round. Points = base + speed bonus (e.g. 100 minus 2 per second elapsed, minimum 20).
Hint 1 at 10s (category or word length), hint 2 at 20s (first letter).
Play N rounds (setting, default 10). Highest total wins.
Word Scramble rules: scramble must never equal the original; scramble is identical for all players; words of length 4 to 9. Emoji Guess rules: each puzzle has emojis, answer, alternatives[], category. Answer checking: normalize with lowercase, trim, strip punctuation and spaces, strip a leading "the". Compare to answer and alternatives. State: { round, prompt, answerNormalized, startedAt, hintsShown, scores, winnerOfRound }. Hidden info: the answer never leaves the server until the round ends.

6.3 Hangman Duel
Players: 2+. One setter, the rest guessers.

Flow:

Setter privately enters a word (letters only, 3 to 15) and an optional category hint.
Guessers pick letters. In group mode they share one pool of 6 wrong guesses; in duel mode it is one guesser.
Correct letters fill every matching blank. Wrong letters draw the next part of the figure.
Guessers win by completing the word. Setter wins if the figure completes.
Setter role rotates each round.
Scoring: guessers earn points for letters revealed and a bonus for solving; setter earns points if the word survives. Validation: reject non-letter words, repeated letters, guesses from the setter. Hidden info: guessers receive only the masked word (_ A _ _ L E).

6.4 Dots and Boxes
Players: 2 to 4. Board: 5x5 boxes by default (6x6 dots), setting for 4x4 to 7x7.

Flow:

Players take turns drawing one line between two adjacent dots.
Completing the fourth side of a box claims it and gives the same player another turn.
Game ends when all lines are drawn. Most boxes wins.
State: { size, lines: Set, boxOwners, turnIndex, scores }. Lines are identified as h-r-c (horizontal) and v-r-c (vertical). Validation: line must exist, be undrawn, and be drawn on the player's turn. Disconnect: after a 30s timeout, the server auto-plays a random safe line for the absent player (or lets the host skip them). Tie: shared win.

6.5 Liar's Dice
Players: 2 to 6. Each starts with 5 dice.

Flow:

Everyone rolls privately.
Starting player makes a bid: quantity and face (e.g. "four 3s").
Next player must either raise the bid (higher quantity, or same quantity with a higher face) or call Liar.
On a Liar call, all dice are revealed. If the actual count of that face (across all players) is at least the bid, the caller loses a die; otherwise the bidder loses one.
Loser of the challenge starts the next round. A player with zero dice is eliminated. Last one standing wins.
House rule options (settings): ones are wild (on/off); "spot on" call (on/off). Hidden info: each player's view contains only their own dice plus others' dice counts. All dice are revealed only in the reveal event. Server tasks: dice rolling uses the server's RNG; bid validation; turn timer (30s) with auto-fold to a Liar call or forced minimum raise.

6.6 Name It Survival
Players: 3 to 10.

Flow:

A topic is chosen (first by the host, afterwards by the player just eliminated).
Players take turns naming one item in that topic. No repeats. Each turn has a 10 second countdown.
A player is out if they time out, repeat an answer, or lose a challenge.
When someone is out, the round ends, the used list resets, and the eliminated player chooses the next topic (they remain a spectator and topic chooser only for that pick, or are fully out for the game; setting).
Last remaining player wins.
Challenge system (default):

Answers are accepted instantly. Any other player can tap Challenge within 5 seconds.
The other players vote Valid or Invalid over 8 seconds. Majority decides; ties go to the answerer.
Invalid means the answerer is out.
Later upgrades: built-in lists for common topics (countries, fruits) to auto-validate; optional AI judge. Normalization: lowercase, trim, strip punctuation, for repeat detection. State: { topic, order[], currentIndex, usedAnswers[], turnDeadline, challenge?, eliminated[] }.

7. Content
File	Contents	Starter size
words.json	{ word, difficulty }	200 words
emoji.json	{ emojis, answer, alternatives, category }	100 puzzles
topics.json	Topic suggestions for Name It	50 topics
hangman-categories.json	Optional category hints	20
Example emoji entry:

{ "emojis": "🦁👑", "answer": "The Lion King", "alternatives": ["Lion King"], "category": "Movie" }
Content is plain JSON, so friends can add inside jokes without touching code.

8. UI and Design
8.1 Principles
Phone portrait first. Large tap targets (minimum 44px), one primary action per screen.
One theme across all games: shared colors, font, and button styles.
No image assets. Use emoji, CSS, and inline SVG.
Animation is last. Every game must be fully playable without it.
8.2 Shared screens
Home: Create Room / Join Room.
Lobby: big room code, invite link, player list, game picker, settings, Start.
Game screen: game-specific, with a thin top bar (room code, scores, leave).
Between rounds: round result and scoreboard.
Final results: winner, session scoreboard, Play Again / Back to Lobby.
8.3 Player avatars
A color plus an emoji or initial. Assigned automatically, no uploads.

8.4 Per-game visuals
Game	Essential	Optional polish
RPS	Three large choice buttons, waiting state, simultaneous reveal	Shake before reveal
Word Scramble	Letter tiles, timer bar, input	Tile slide on correct
Emoji Guess	Large emojis, category tag, timer	Hint reveal animation
Hangman	SVG figure in 6 stages, blanks, keyboard with used letters greyed	Gallows swing
Dots and Boxes	SVG dot grid, tappable lines, colored boxes	Fill animation
Liar's Dice	Dice faces (CSS), hidden dice for opponents, bid picker, reveal screen	Rolling animation
Name It Survival	Current player highlight, countdown ring, used answers list, challenge/vote modal	Sound or shake on elimination
8.5 Accessibility
Do not rely on color alone (add shapes or labels); text size scalable; high contrast; tap targets large.

8.6 Optional big-screen mode
A read-only /screen/ABCD route for a TV or laptop showing the lobby, scoreboard, and public parts of each game. Phones remain the controllers. Not required for v1.

9. Project Structure
party-pack/
├── client/
│   └── src/
│       ├── App.tsx
│       ├── socket.ts              # connection + token handling
│       ├── components/            # Lobby, Scoreboard, Timer, PlayerChip
│       ├── games/
│       │   ├── rps/
│       │   ├── guessRace/
│       │   ├── hangman/
│       │   ├── dotsAndBoxes/
│       │   ├── liarsDice/
│       │   └── nameIt/
│       └── styles/theme.css
├── server/
│   └── src/
│       ├── index.ts               # Express + Socket.IO bootstrap
│       ├── rooms.ts               # room lifecycle, codes, reconnection
│       ├── games/
│       │   ├── registry.ts        # maps gameId to module
│       │   ├── rps.ts
│       │   ├── guessRace.ts
│       │   ├── hangman.ts
│       │   ├── dotsAndBoxes.ts
│       │   ├── liarsDice.ts
│       │   └── nameIt.ts
│       └── content/*.json
├── shared/
│   └── types.ts                   # event and view types
└── README.md
10. Security and Fair Play
Validate every action server-side: right player, right phase, valid data.
Never send secrets (dice, words, answers) to unauthorized clients.
Rate-limit actions (for example, max 5 guesses per second per player).
Sanitize nicknames and typed text; render as text, never as HTML.
Restrict CORS to the client's domain.
Use cryptographically random room codes and tokens where practical.
11. Testing
Level	What	Tool
Unit	Each game module's pure functions: bid validation, box completion, answer normalization	Vitest/Jest
Integration	Two or more socket clients play a full game against a local server	Socket.IO client in tests
Manual	Real phones, refresh mid-game, airplane-mode reconnect, host leaves	Checklist
Because modules are pure (state + action → new state), most game logic can be tested without any network.

Manual checklist (per game): start with minimum players; each player's view hides secrets; refresh mid-round restores the seat; host leaving transfers host; timeout behavior; game ends cleanly and returns to lobby.

12. Deployment
Server: deploy to Render or Railway as a Node web service, with a PORT env var and a CLIENT_ORIGIN env var.
Client: deploy to Vercel or Netlify with VITE_SERVER_URL pointing to the server.
Free-tier note: servers may sleep when idle, so the first connection can take 30 to 60 seconds. A simple "waking up the server" message on the home screen handles this.
Scaling: one instance is enough. If you ever run multiple instances, rooms would need sticky sessions or shared state (Redis); out of scope for v1.
13. Roadmap
Phase	Deliverable	Proves
1	Foundation + Rock-Paper-Scissors	Rooms, lobby, realtime sync, reconnection
2	Guess Race (Word Scramble + Emoji Guess)	Timers, simultaneous input, content files
3	Hangman Duel	Hidden information, role rotation
4	Dots and Boxes	Turn order, board rendering
5	Liar's Dice	Private per-player state, elimination
6	Name It Survival	Turn timers, voting
7	Polish	Animations, sounds, big-screen mode, more content
Each phase ends in something playable with friends.

14. Risks and Mitigations
Risk	Impact	Mitigation
Players disconnect mid-game	Game stalls	Reconnect tokens, per-game timeout rules, host skip
Free server cold starts	Slow first join	Wake-up message, optional uptime ping
Disputed answers (Name It)	Arguments	Challenge-and-vote system
Content runs out	Repetition	Easy JSON editing, no-repeat within a session
Scope creep	Never ships	Phase plan; one game at a time
15. Open Decisions
Play setting: same room, remote, or both (affects whether to build big-screen mode early).
Name It elimination: is an eliminated player fully out, or do they stay as spectators who still choose the next topic?
Group Hangman: shared wrong-guess pool, or turn-based guessing?
Dots and Boxes default board size.
Content language: English only, or additional languages?
House rules defaults for Liar's Dice (wild ones, spot-on).
16. Glossary
Room: a session identified by a 4-letter code.
Host: the player who created the room and controls game selection.
Module: a self-contained game implementing the shared interface.
View: the per-player snapshot of game state the server sends.
Action: a message from a client asking to do something in a game.
Server-authoritative: the server decides what is true; clients only request.
