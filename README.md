# Boredom

A real-time party game collection for friends and family. One person creates a room, everyone
joins on their phone with a 4-letter code, and the host picks a game.

```
boredom/
├── core/       Django backend: rooms and game logic, served over one WebSocket (/ws/)
├── frontend/   React app (Vite + TypeScript): what players see in the browser
└── shared/     constants.json, used by both sides
```

---

## What you can see today

| Part | Status |
| --- | --- |
| Rooms: create, join by code or invite link, lobby, reconnect after refresh | **Playable** |
| Rock-Paper-Scissors (duel or bracket) | **Playable** |
| Guess Race (Word Scramble and Emoji Guess) | **Playable** |
| Hangman Duel | **Playable** |
| Dots and Boxes (2–4 players) | **Playable** |
| Liar's Dice (2–6 players) | **Playable** |
| Name It Survival (3–10 players) | **Playable** |
| Optional accounts: save your profile, log in on any device, keep your avatar and stats | **Working** |
| Admin dashboard (players, games, leaderboards, activity, CSV) at `/manage/` | **Working** |

## How to play (once both servers are running, steps 4 and 6)

1. Open **http://localhost:5173** and set up your profile: a nickname and a color. Each room gives you a random avatar.
   Optional: on **Your profile**, create a free account to keep your name, avatar and stats on any
   device (already have one? use **I already have an account** on the first screen). Players with an
   account show a ✓ badge.
2. Press **Create room**. You land in the lobby with a big 4-letter room code.
3. Add a second player. Every game needs at least 2.
   - **On the same computer:** open a **private/incognito window** (or another browser) at
     http://localhost:5173, set up a second profile, press **Join room** and type the code.
     A normal second tab shares the first tab's profile and saved seat, so use a private window.
   - **On a phone:** see step 7, then open the invite link or type the code.
4. As the host, tap a game card, adjust its settings, and press **Start game**.
5. When the game ends, the host picks **Play again** or **Back to lobby**. Scores add up
   across games on the session scoreboard: every game gives the winner 100 points and last
   place 0 (ties share), so each game counts the same.

---

## 1. Install the tools (once)

| Tool | Version | Check with |
| --- | --- | --- |
| Python | 3.11 or newer | `python3 --version` |
| Node.js | 20.19+ or 22.12+ | `node --version` |
| npm | comes with Node | `npm --version` |
| Git | any | `git --version` |

## 2. Get the code on the right branch

```bash
cd ~/boredom
git branch            # shows the branch you are on
git switch frontend   # the newest work (backend + frontend so far)
```

## 3. Set up the backend (once)

Run these from the repo root (`~/boredom`):

```bash
python3 -m venv myenv                      # create a virtual environment (skip if myenv/ exists)
source myenv/bin/activate                  # your prompt now starts with (myenv)
pip install -r core/requirements.txt       # install Django, Channels, Daphne, ...
cd core
DJANGO_DEBUG=true python manage.py migrate # create the accounts database (core/db.sqlite3)
cd ..
```

Run `python manage.py migrate` again (from `core/`, with the exports from step 4) whenever you
pull new code; it is safe to repeat.

## 4. Start the backend (terminal 1)

The server refuses to start without these two variables, so set them first:

```bash
cd ~/boredom
source myenv/bin/activate
export DJANGO_DEBUG=true
export DJANGO_SECRET_KEY=dev-only-change-me-to-a-long-random-string
cd core
python manage.py runserver
```

Leave this terminal open. You should see `Starting ASGI/Daphne ... development server at http://127.0.0.1:8000/`.

If you see "You have unapplied migrations", stop the server and run `python manage.py migrate`
(step 3). Rooms and games live in memory; the database only holds optional player accounts.

**Check it:** open http://localhost:8000/api/health in a browser. It must show `{"ok": true}`.

> `runserver` is for development: it restarts itself when code changes.
> The production command is `daphne -b 0.0.0.0 -p $PORT config.asgi:application` (run from `core/`).
> Always run **exactly one** backend process. Rooms live in that process's memory.

### Database (player accounts)

Accounts (username, saved profile, per-game stats) are stored in a database chosen by
`DATABASE_URL`:

| Where | `DATABASE_URL` | Notes |
| --- | --- | --- |
| Your computer | not set | SQLite file `core/db.sqlite3`, created by `migrate`. Not in git. |
| Production | `postgres://USER:PASSWORD@HOST:5432/DBNAME` | Use **Postgres** (the driver, `psycopg`, is in `requirements.txt`). SQLite is not suitable for a deployed server. |

On every deploy, run `python manage.py migrate` (from `core/`) **before** starting Daphne.
Production also needs a long random `DJANGO_SECRET_KEY` (50+ characters): it signs the login
tokens, so changing it logs every player out. Generate one with
`python -c "import secrets; print(secrets.token_urlsafe(50))"`.

### Admin dashboard

A staff-only dashboard (Django admin) shows every player's activity: Overview, Games, Users,
Leaderboards, Activity feed and CSV exports.

**Create the admin account** (once; this account is *not* a game account and cannot be made
by signing up in the game):

```bash
cd ~/boredom/core
python manage.py createsuperuser      # pick a username and a long password
```

Then open **http://localhost:5173/admin** (the dashboard in the app) and press **Log in as staff**,
or use the classic Django pages at http://localhost:8000/manage/. Both show the same numbers. Staff accounts made later in the admin
(Users → tick "Staff status") can see every dashboard page; only superusers can delete
activity rows.

| Setting | Default | Notes |
| --- | --- | --- |
| `ADMIN_URL_PREFIX` | `manage/` | Where the admin lives. In production pick something unguessable, e.g. `staff-7f3k2/`. |
| `TIME_ZONE` | `UTC` | Times are stored in UTC and shown in this zone (e.g. `Africa/Accra`). |
| `CSRF_TRUSTED_ORIGINS` | none | Production: your backend's public origin, e.g. `https://api.example.com`, or admin logins fail with a CSRF error. |

The app dashboard (`/admin`) uses the Django admin login session, so in production the frontend
and the backend must share one origin (serve the built frontend and proxy `/api`, `/ws`, `/manage`
and `/static` to Django from the same domain). On separate domains, use `/manage/` instead.
After pulling this change, restart `npm run dev` so the dev server picks up the new `/manage` proxy.

Production notes:
- Run `python manage.py collectstatic --noinput` on every deploy (WhiteNoise serves the admin's
  CSS and JS from `core/staticfiles/`).
- With `DJANGO_DEBUG` off, admin cookies are HTTPS-only and the server trusts the proxy's
  `X-Forwarded-Proto` header. Let your host redirect HTTP to HTTPS (and enable HSTS there).
- Five wrong admin passwords for the same username from one IP lock that pair out for 15 minutes.

**Privacy and retention.** Guests are tracked only by a pseudonymous key (a keyed hash of their
browser profile id), so guest numbers are approximate: one browser = one guest. No IP addresses,
user agents, passwords, tokens or game secrets are stored. Activity events are deleted after
`ACTIVITY_RETENTION_DAYS` (180) days, once a day and at start-up; game sessions and results are
kept forever so totals stay correct. Deleting an account (by the player or from the admin)
removes the login, profile and stats and turns their past games into "Deleted player".

**Back up the database.** The dashboard history and every player account live only in the
database (`DATABASE_URL`). Turn on your host's automatic Postgres backups; a lost database
cannot be rebuilt from anything else. Never commit `core/db.sqlite3`.

**Metric definitions**

| Metric | Definition |
| --- | --- |
| Completed game | A game that reached its end (`gameOver`). |
| Abandoned game | A game whose room closed mid-game (everyone left, or idle cleanup). Excluded from wins, losses and rates. |
| Win | A completed game finished in placement 1. Ties for 1st all count as wins. |
| Loss | A completed game finished below placement 1, including players who left or timed out. |
| Win rate | Wins / completed games, shown only after 5 completed games (`DASHBOARD_MIN_GAMES_FOR_RATES`); otherwise "—". |
| Games (per player) | Completed games played. |
| Registered users | Accounts with a game profile (admin-only accounts are not counted). |
| Guests seen | Distinct guest keys with activity or games in the selected range. |
| New signups | Accounts created in the selected range. |
| Daily / weekly / monthly active | Distinct accounts + guests with any activity event in the last 1 / 7 / 30 days (rolling). |
| Games today | Completed games started since midnight in `TIME_ZONE`. |
| Avg players / Avg duration | Over completed games in the range. |
| Abandon rate | Abandoned / (completed + abandoned) in the range. Completion rate is the opposite. |
| Unique players (per game) | Distinct accounts + guest keys in completed games of that game. |
| Most played / most won / most lost | Highest completed games / wins / losses. Ties: most won prefers the higher win rate, most lost the lower win rate, then the game name. |
| Favorite game | The player's most-played completed game (ties: game id). |
| Top co-players | Players sharing the most completed games; "ahead/behind" compares placements in those games. |
| First / last seen | Accounts: sign-up date / latest activity or game. Guests: first / last game (guests are listed once they have played). |
| Live now | Rooms open in server memory right now (never shows game secrets). |

## 5. Set up the frontend (once)

Open a **second terminal**:

```bash
cd ~/boredom/frontend
npm ci        # installs the exact package versions from package-lock.json
```

## 6. Start the frontend (terminal 2)

```bash
cd ~/boredom/frontend
npm run dev
```

You should see something like:

```
  ➜  Local:   http://localhost:5173/
  ➜  Network: http://192.168.1.5:5173/
```

Open **http://localhost:5173**. You should see the **Boredom** home page with **Create room** and
**Join room**. Then follow "How to play" at the top of this file.

The frontend dev server forwards `/api` and `/ws` to the backend on port 8000, so both terminals
must be running.

## 7. Open it on your phone (optional)

1. Make sure your phone is on the **same Wi-Fi** as your computer.
2. Find the `Network:` address that `npm run dev` printed, for example `http://192.168.1.5:5173`.
3. Stop the backend (Ctrl+C in terminal 1). Restart it with your computer's IP added to the
   allowed hosts, or the phone's live connection is refused:

   ```bash
   export DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1,192.168.1.5
   python manage.py runserver
   ```

4. Open the `Network:` address on your phone.

## 8. Run the automated tests

```bash
# Backend (terminal with myenv active, from ~/boredom/core)
pytest
ruff check .
python manage.py accounts_smoke   # register, log in and join rooms end to end (needs migrate)

# Frontend (from ~/boredom/frontend)
npm run lint
npm run typecheck
npm test
npm run build

# Optional: play real games through the UI against the running backend (step 4 must be running)
LIVE_BACKEND=1 npx vitest run -c vitest.live.config.ts
```

---

## Troubleshooting

| Problem | Fix |
| --- | --- |
| `ImproperlyConfigured: DJANGO_SECRET_KEY must be set` | You skipped the two `export` lines in step 4. Run them in the same terminal, then start again. |
| `Error: That port is already in use` (or `Address already in use`) | A backend is already running, maybe in another terminal. Use that one, or stop it with Ctrl+C there. |
| "Can't reach the server" when creating or joining | The backend is not running. Start it (step 4), then try again. |
| Works on the computer, but the phone says it can't reach the server | Add your computer's IP to `DJANGO_ALLOWED_HOSTS` (step 7). |
| A second tab on the same computer takes over your seat | Tabs share one profile and saved seat. Use a private/incognito window for a second player. |
| `no such table: accounts_profile` (or `auth_user`) | Run `python manage.py migrate` from `core/` (step 3). |
| A logged-in player suddenly plays as a guest | Their login expired (30 days) or `DJANGO_SECRET_KEY` changed. They log in again. |
| `pip install` fails | Activate the venv first: `source myenv/bin/activate`. |
| npm or Vitest crashes oddly (for example `Bus error` or `Cannot find module`) | The installed packages are damaged. Reinstall them: `cd frontend && rm -rf node_modules && npm ci`. |
| `command not found: daphne` / `pytest` | The venv is not active in this terminal: `source ~/boredom/myenv/bin/activate`. |

## More documentation

- `core/PROTOCOL.md`: the exact WebSocket messages and the account HTTP API, for developers.
- The "Admin dashboard" section above: how to reach it and what every number means.
- `documentation.md`: the original game design document.
