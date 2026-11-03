# Nemesis

Nemesis lets registered players put real money in a wallet so they can play friends for stakes.
This guide covers Part 1: the wallet, age checks, deposits, withdrawals, limits and the staff
tools. Staked games (challenges) come in Part 2.

Contents:

1. [How it works in one minute](#1-how-it-works-in-one-minute)
2. [Turning it on (server)](#2-turning-it-on-server)
3. [Setting up staff](#3-setting-up-staff)
4. [What players do](#4-what-players-do)
5. [What staff do](#5-what-staff-do)
6. [Money rules](#6-money-rules)
7. [Limits and safety](#7-limits-and-safety)
8. [Privacy](#8-privacy)
9. [Settings you can change](#9-settings-you-can-change)
10. [For developers](#10-for-developers)
11. [Troubleshooting](#11-troubleshooting)

---

## 1. How it works in one minute

- Nemesis is **off for everyone** until the server turns it on, and then **off for each player**
  until they turn it on in their profile.
- A player proves they are **18 or older** by uploading an ID. A staff member checks it.
- Money moves **by hand**. The player sends mobile money to our account with a reference code;
  staff confirm it arrived and credit the wallet. Withdrawals work the other way: staff send the
  money and mark the request paid.
- Every change to a balance is written to a **ledger** that always adds up to zero, so we can
  prove where every pesewa went.
- All amounts are whole **pesewas** (GHS 1.00 = 100). The server does every calculation; the
  app only shows the numbers.

## 2. Turning it on (server)

The server reads these environment variables when it starts:

| Variable | Default | What it does |
| --- | --- | --- |
| `NEMESIS_ENABLED` | off | The master switch. Off: players see nothing, and every player wallet route except status returns 404. |
| `PRIVATE_UPLOAD_DIR` | `<repo>/private_uploads` | Where ID photos are saved. Must not be a folder the web server serves. |
| `DUAL_APPROVAL_ENABLED` | off | On: big money actions and all corrections, merchant changes and switch changes need a second staff member. |

Steps:

```bash
export NEMESIS_ENABLED=true
export PRIVATE_UPLOAD_DIR=/srv/boredom/private_uploads
cd core
python manage.py migrate
# then restart the server (runserver in development, your ASGI process in production)
```

To check it worked, call `GET /api/nemesis/status` with a player's token. The reply should say
`"enabled": true`.

To turn it off again, unset `NEMESIS_ENABLED` and restart. Balances and history are kept, and
staff can still pay out waiting withdrawals.

## 3. Setting up staff

Money tools live in the staff dashboard at `/admin`.

**Permissions.** Give staff only what they need, using groups in the Django admin
(`/manage/` by default). Superusers have everything.

| Permission | Lets them |
| --- | --- |
| `review_ids` | See ID photos, approve or reject IDs |
| `review_deposits` | Approve or reject deposits, enter reconciliation reports |
| `review_withdrawals` | Approve, pay out and reject withdrawals |
| `adjust_balances` | Propose and approve corrections, remove a permanent break |
| `edit_merchant` | Change the account players pay into |
| `edit_flags` | Pause or resume deposits, withdrawals and staking |

**Two-factor (required).** Each staff member opens `/admin` → **Security**, scans the QR code
with an authenticator app (Google Authenticator, Authy, 1Password…), enters a code and saves the
10 backup codes. Then they log out and back in with a code. Money pages stay hidden until then.

**Step-up.** Sensitive actions (approving anything, viewing ID photos, changing settings) ask for
a fresh code if the last one was more than 5 minutes ago.

**Receiving account.** In `/admin` → **Money settings**, enter the network, number and account
name players should pay into. Players cannot deposit until this is set.

## 4. What players do

Everything happens in the **Nemesis** section of `/profile`. Guests never see it, and Nemesis is
not mentioned anywhere else in the app.

**Verify age** → **Turn on** → **Add funds / Withdraw**.

1. **Verify your age.** Choose the ID type, enter the name, ID number and date of birth, and add
   a photo of the front (back is optional). Then wait for a staff member to review it.
   - Rejected: the player sees the reason and can try again (3 attempts in total).
   - Under 18: rejected for good straight away.
2. **Turn on Nemesis.** Allowed once the ID is approved, the account is at least 24 hours old
   and the player has played at least 5 games. The player reads the rules and ticks two boxes.
   Nobody gets free credit.
3. **Add funds.**
   1. Enter an amount.
   2. The app shows our account details, the exact amount and a reference like `NEM-7KQ2XP`.
   3. The player pays from their phone and **puts the reference in the payment note**.
   4. They enter the transaction ID and the number they paid from.
   5. The app waits (checking every 20 seconds) until staff approve it.
   An unpaid request expires after 60 minutes. If the player refreshes, the request picks up
   where it left off.
4. **Withdraw.**
   1. Set where to receive money. This needs their password.
   2. Enter an amount and confirm.
   3. The money is held at once, and staff pay it out by hand.
   The first withdrawal waits 24 hours. Changing the payout number waits 48 hours, so a stolen
   login cannot redirect money quickly.
5. **History, Limits, Take a break, Turn off.** See [section 7](#7-limits-and-safety). Turning
   off keeps the balance, and the player can still withdraw.

## 5. What staff do

| Page | Daily job |
| --- | --- |
| **Money** | Check the overview. A **red banner** means something needs attention now. |
| **IDs** | Open a submission, view the photo, check the name and number, type the date of birth you read, approve or reject with a reason. |
| **Deposits** | For each pending deposit, **find the payment in the receiving account itself** (not a screenshot). Match the reference, transaction ID and amount. Tick "I verified this payment…", confirm the amount received, and approve. If the amount differs, add a note; only what arrived is credited. |
| **Withdrawals** | Approve once the eligible time has passed. Check the payout name matches the name on the ID. Send the money, then **Mark paid** with the payout reference. Reject returns the money to the player. |
| **Reconciliation** | At least once a day, enter the real combined balance of the receiving accounts. If it is lower than what players are owed, the report is marked short. |
| **Adjustments** | Fix mistakes by adding a correction with a reason. Existing records are never edited. |
| **Money settings** | Change the receiving account; pause deposits or withdrawals. |
| **Money audit** | See who did what. Every action is logged. |

Rules that always apply:

- Staff can never approve their own deposit, withdrawal or ID.
- Approving the same deposit twice does nothing the second time.
- With dual approval on, a second, different staff member must approve:
  - deposits and withdrawals of **GHS 500.00 or more**;
  - every correction, receiving-account change and switch change.

## 6. Money rules

The ledger has these account types:

| Account | Meaning |
| --- | --- |
| user | A player's available balance |
| withdrawal_hold | Money a player asked to withdraw, not yet paid |
| external | The outside world. It goes negative as money comes in, so its size is what we hold for players |
| escrow, fees | Used by staked games in Part 2 |

How money moves:

| Event | From → To |
| --- | --- |
| Deposit approved | external → user |
| Withdrawal requested | user → withdrawal_hold |
| Withdrawal paid | withdrawal_hold → external |
| Withdrawal cancelled or rejected | withdrawal_hold → user |
| Correction | external ↔ user |

Guarantees:

- Every transaction adds up to zero.
- No balance except external can go below zero.
- Ledger entries are never changed or deleted.
- Each action has a fixed key, so retrying it never moves money twice.
- Checks are written for PostgreSQL row locks; use PostgreSQL in production.

**Owed to players** (liabilities) = all user + withdrawal_hold + escrow + fees balances. The real
money in the receiving accounts should never be less than this.

**Ledger check.** Run `python manage.py check_ledger` at any time. The server also runs it daily
and logs an ERROR if anything is off, and the Money page shows a red banner.

## 7. Limits and safety

| Rule | Default |
| --- | --- |
| Deposit amount | GHS 10.00 to GHS 1,000.00 each |
| Deposit limit | GHS 2,000.00 a day, GHS 10,000.00 in 30 days (players can set lower) |
| Open deposits | One at a time |
| Withdrawal | At least GHS 20.00; at most GHS 1,000.00 a day; one waiting at a time |

**Player limits.** A player can lower their limits at any time, and it applies at once. Raising
them takes effect after 24 hours.

**Take a break.** Players can take a break for 7 days, 30 days or permanently. It starts at once
and cannot be shortened.
- Blocked during a break: deposits and turning Nemesis on (and, in Part 2, staking).
- Still allowed: withdrawing and viewing history.
- Only staff can lift a permanent break (user page → **Remove permanent exclusion**, logged).

**Account deletion.** An account cannot be deleted while it has a balance, held money, or an open
deposit or withdrawal. The player or staff gets `HAS_FUNDS`.

**Pause switches.** Staff can pause deposits or withdrawals instantly from Money settings without
turning the whole feature off.

## 8. Privacy

- **ID number:** we keep only a scrambled fingerprint (HMAC) and the last 4 characters. The
  fingerprint stops one ID being used by two accounts.
- **ID photos:** stored under random names in the private folder. They are never reachable by a
  public link, only by staff with permission and a fresh code, and every view is logged. They
  are deleted 30 days after the decision, or at once if the account is deleted.
- **Nemesis data** (balance, status, anything) is never sent over the game connection or shown to
  other players.
- **Disclosure:** the "What we record" list on `/about` and `/profile` tells players about ID data
  and wallet records.

## 9. Settings you can change

Defaults live in `shared/constants.json` (amounts in pesewas). Restart and rebuild after editing.

| Constant | Default | Meaning |
| --- | --- | --- |
| `NEMESIS_MIN_ACCOUNT_AGE_HOURS` | 24 | Account age before turning on |
| `NEMESIS_MIN_GAMES` | 5 | Games played before turning on |
| `NEMESIS_MIN_AGE_YEARS` | 18 | Minimum age |
| `NEMESIS_RULES_VERSION` | 1 | Raise it when the rules text changes; players re-accept |
| `ID_MAX_BYTES` / `ID_MAX_ATTEMPTS` | 5 MB / 3 | Photo size, ID tries |
| `ID_IMAGE_RETENTION_DAYS` | 30 | Days before photos are deleted (0 keeps them) |
| `DEPOSIT_MIN` / `DEPOSIT_MAX` | 1000 / 100000 | Per deposit |
| `DEPOSIT_DAILY_LIMIT` / `DEPOSIT_30D_LIMIT` | 200000 / 1000000 | Platform maximums |
| `DEPOSIT_REQUEST_TTL_MIN` | 60 | Minutes before an unpaid deposit expires |
| `WITHDRAW_MIN` / `WITHDRAW_DAILY_CAP` | 2000 / 100000 | Withdrawal limits |
| `WITHDRAW_FIRST_DELAY_HOURS` | 24 | Wait on the first withdrawal |
| `PAYOUT_CHANGE_DELAY_HOURS` | 48 | Wait after changing payout details |
| `LIMIT_RAISE_DELAY_HOURS` | 24 | Wait before a raised limit applies |
| `DUAL_APPROVAL_THRESHOLD` | 50000 | Amount that needs two staff (when dual approval is on) |
| `STEP_UP_MINUTES` | 5 | How long a step-up code lasts |
| `PAYMENT_NETWORKS` | MTN MoMo, Telecel Cash, AirtelTigo Money, Bank transfer | Networks offered |

## 10. For developers

**Code map** (`core/nemesis/`):

| File | Holds |
| --- | --- |
| `models.py` | All tables |
| `ledger.py` | The **only** code that changes balances (`post_transaction`, `reconcile`) |
| `ids.py` | ID checks, private storage, retention |
| `services.py` | Status, eligibility, turning on and off, wallet summary |
| `wallet.py` | Deposits, withdrawals, payout details, limits, breaks |
| `review.py` | Staff decisions |
| `staff.py`, `totp.py` | Two-factor and step-up (standard library only) |
| `views.py`, `admin_api.py` | HTTP endpoints |
| `tasks.py` | Background jobs: ledger check and photo deletion daily, deposit expiry every 5 minutes |

Frontend: `frontend/src/lib/nemesis.ts`, `frontend/src/pages/profile/nemesis/` (player), and
`frontend/src/admin/money/` plus `frontend/src/admin/pages/money/` (staff).

**Full API reference:** `core/PROTOCOL.md`, section 14 (player) and section 15 (staff). In short:

- Player routes need the Bearer token, under `/api/nemesis/…` and `/api/wallet/…`. Every POST
  accepts an `Idempotency-Key` header so retries are safe.
- Staff routes use the dashboard session plus CSRF, under `/api/admin/2fa/…`, `/api/admin/ids/…`
  and `/api/admin/money/…`.
- Errors look like `{"error": {"code", "message", "fields"?}}`.

**Tests:** `core/tests/test_nemesis_*.py` and `frontend/src/pages/profile/nemesis.test.tsx`,
`frontend/src/admin/money.test.tsx`. The two concurrency tests only run on PostgreSQL:

```bash
DATABASE_URL=postgres://user:pass@localhost/boredom_test pytest tests/test_nemesis_ledger.py tests/test_nemesis_admin.py
```

## 11. Troubleshooting

| Problem | Fix |
| --- | --- |
| Players don't see Nemesis | `NEMESIS_ENABLED` isn't reaching the server process. Check status returns `enabled: true`. Guests never see it. |
| "Turn on" is greyed out | The button says why: more games, account too new, or on a break. |
| "Deposits are not available right now" | No active receiving account. Set it in Money settings, or deposits are paused. |
| Staff can't see money pages | Set up two-factor on Security, then log out and in with a code. Check their permissions. |
| "Confirm it's you" keeps appearing | Step-up lasts 5 minutes; enter a new code. Codes can't be reused within 30 seconds. |
| Staff member lost their phone | Log in with a backup code. To reset, run `python manage.py shell -c "from nemesis.models import StaffSecurity; StaffSecurity.objects.filter(user__username='NAME').delete()"`; they then set up again on Security. |
| Red banner: report missing or short | Enter today's real balance on Reconciliation. If short, find the gap before approving payouts. |
| Red banner: ledger check failed | Run `python manage.py check_ledger` to see which accounts differ. Do not approve money actions until it's fixed. |
| Can't delete an account (`HAS_FUNDS`) | The player must withdraw everything, and open requests must be finished first. |
