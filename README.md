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

The project is built in phases. **The game screens are not built yet**, so no game can be played
in the browser at the moment. This is expected, not a setup problem.

| Part | Status | What you'll see |
| --- | --- | --- |
| Backend rooms and lobby logic | Done | Nothing visual. It is an API. |
| Backend games: Rock-Paper-Scissors, Guess Race, Hangman | Done | Nothing visual. Tested by 271 automated tests. |
| Backend games: Dots and Boxes, Liar's Dice, Name It | Not started | — |
| Frontend F0: setup | Done | A **connection check** page at `/`. |
| Frontend F1–F3: profiles, home, lobby, invites | Next | — |
| Frontend F4+: game screens | After F3 | The games become playable here. |

When you follow this guide, success today means the connection check page shows
**✓ Online** and **✓ Connected**.

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
```

## 4. Start the backend (terminal 1)

The server refuses to start without these two variables, so set them first:

```bash
cd ~/boredom
source myenv/bin/activate
export DJANGO_DEBUG=true
export DJANGO_SECRET_KEY=dev-only-change-me
cd core
python manage.py runserver
```

Leave this terminal open. You should see `Starting ASGI/Daphne ... development server at http://127.0.0.1:8000/`.

A warning about "unapplied migrations" is harmless: the game does not use the database.

**Check it:** open http://localhost:8000/api/health in a browser. It must show `{"ok": true}`.

> `runserver` is for development: it restarts itself when code changes.
> The production command is `daphne -b 0.0.0.0 -p $PORT config.asgi:application` (run from `core/`).
> Always run **exactly one** backend process. Rooms live in that process's memory.

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

Open **http://localhost:5173**. The connection check page should show:

- **Server: ✓ Online**: the frontend reached the backend's `/api/health`.
- **Live connection: ✓ Connected**: the WebSocket to `/ws/` works.

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

# Frontend (from ~/boredom/frontend)
npm run lint
npm run typecheck
npm test
npm run build
```

---

## Troubleshooting

| Problem | Fix |
| --- | --- |
| `ImproperlyConfigured: DJANGO_SECRET_KEY must be set` | You skipped the two `export` lines in step 4. Run them in the same terminal, then start again. |
| `Error: That port is already in use` (or `Address already in use`) | A backend is already running, maybe in another terminal. Use that one, or stop it with Ctrl+C there. |
| Page shows **✕ Not reachable** / **✕ Disconnected** | The backend is not running. Start it (step 4), then press **Retry**. |
| Works on the computer, but the phone shows **✕ Disconnected** | Add your computer's IP to `DJANGO_ALLOWED_HOSTS` (step 7). |
| `pip install` fails | Activate the venv first: `source myenv/bin/activate`. |
| npm or Vitest crashes oddly (for example `Bus error` or `Cannot find module`) | The installed packages are damaged. Reinstall them: `cd frontend && rm -rf node_modules && npm ci`. |
| `command not found: daphne` / `pytest` | The venv is not active in this terminal: `source ~/boredom/myenv/bin/activate`. |

## More documentation

- `core/PROTOCOL.md`: the exact WebSocket messages, for developers.
- `documentation.md`: the original game design document.
