"""Staff-only JSON API for the React admin dashboard (/admin in the frontend).

Authentication is the Django admin session: staff log in at /<ADMIN_URL_PREFIX>login/ and the
browser sends the session cookie (same origin). POST actions need the CSRF token from
GET /api/admin/session in an X-CSRFToken header. Every error is {"error": {"code", "message"}}.

The numbers come from the same functions as the server-rendered dashboard, so both agree.
No response contains passwords, tokens, raw profile ids, seat ids or IP addresses.
"""

import json
from collections.abc import Callable
from datetime import date, datetime
from decimal import Decimal
from functools import wraps
from typing import Any

from django.conf import settings
from django.contrib import admin
from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.paginator import Paginator
from django.db.models import Case, IntegerField, Q, Value, When
from django.http import HttpRequest, JsonResponse
from django.middleware.csrf import get_token
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views.decorators.csrf import ensure_csrf_cookie

from accounts import admin as accounts_admin
from analytics import dashboard, metrics, people
from analytics.models import ActivityEvent, GameSession
from games.constants import DASHBOARD_MIN_GAMES_FOR_RATES, DASHBOARD_PAGE_SIZE, REPORT_REASONS
from social.errors import SocialError
from social.models import RESOLVED_NOTE_MAX, Report
from social.services import clean_note

View = Callable[..., JsonResponse]


def jsonable(value: Any) -> Any:
    """Dates and datetimes as ISO strings, Decimals as floats, recursively."""
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {k: jsonable(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [jsonable(v) for v in value]
    return value


def ok(data: dict[str, Any]) -> JsonResponse:
    return JsonResponse(jsonable(data))


def fail(status: int, code: str, message: str, **extra: Any) -> JsonResponse:
    return JsonResponse({"error": {"code": code, "message": message, **extra}}, status=status)


def login_url() -> str:
    return reverse("admin:login")


def staff_api(method: str = "GET") -> Callable[[View], View]:
    """Staff only (anonymous: 401 with loginUrl; logged in but not staff: 403)."""

    def decorate(view: View) -> View:
        @wraps(view)
        def wrapper(request: HttpRequest, *args: Any, **kwargs: Any) -> JsonResponse:
            user = request.user
            if not user.is_authenticated:
                return fail(401, "UNAUTHORIZED", "Log in as staff.", loginUrl=login_url())
            if not (user.is_active and user.is_staff):
                return fail(403, "FORBIDDEN", "Staff only.", loginUrl=login_url())
            if request.method != method:
                return fail(405, "METHOD_NOT_ALLOWED", f"Use {method}.")
            return view(request, *args, **kwargs)

        return wrapper

    return decorate


def _range(request: HttpRequest) -> tuple[metrics.DateRange, dict[str, Any]]:
    rng = metrics.parse_range(request.GET.get("range"))
    return rng, {
        "range": {"key": rng.key, "label": rng.label},
        "ranges": [{"key": k, "label": v} for k, v in metrics.RANGES.items()],
    }


def _games_list() -> list[dict[str, str]]:
    return [{"id": g, "name": metrics.game_name(g)} for g in metrics.known_game_ids()]


def _game_ref(game_id: str | None) -> dict[str, str] | None:
    return {"id": game_id, "name": metrics.game_name(game_id)} if game_id else None


def _actor(user_id: int | None, guest_key: str, name: str | None) -> dict[str, Any]:
    if user_id is not None:
        return {"kind": "registered", "userId": user_id, "guestKey": None, "name": name or "Player"}
    return {
        "kind": "guest",
        "userId": None,
        "guestKey": guest_key,
        "shortKey": guest_key[:8],
        "name": name or "Guest",
    }


def _per_day(series) -> list[dict[str, Any]]:
    return [{"date": day, "count": n} for day, n in series]


def _page(request: HttpRequest, rows) -> tuple[Any, dict[str, Any]]:
    page = Paginator(rows, DASHBOARD_PAGE_SIZE).get_page(request.GET.get("page"))
    return page, {
        "page": page.number,
        "numPages": page.paginator.num_pages,
        "count": page.paginator.count,
        "pageSize": DASHBOARD_PAGE_SIZE,
    }


# ----- session -----------------------------------------------------------------------


@ensure_csrf_cookie
def session(request: HttpRequest) -> JsonResponse:
    """Who is logged in (open to everyone), the CSRF token and the admin URLs."""
    user = request.user
    staff = bool(user.is_authenticated and user.is_active and user.is_staff)
    return ok(
        {
            "staff": staff,
            "username": user.get_username() if staff else None,
            "superuser": bool(staff and user.is_superuser),
            "csrfToken": get_token(request),
            "loginUrl": login_url(),
            "logoutUrl": reverse("admin:logout"),
            "adminUrl": reverse("admin:index"),
            "exports": {
                "users": reverse("admin:dashboard-export-users"),
                "sessions": reverse("admin:dashboard-export-sessions"),
            },
            "timeZone": settings.TIME_ZONE,
            "minGamesForRates": DASHBOARD_MIN_GAMES_FOR_RATES,
            "openReports": open_reports() if staff else None,
        }
    )


# ----- Overview and Games ------------------------------------------------------------


@staff_api()
def overview(request: HttpRequest) -> JsonResponse:
    rng, ctx = _range(request)
    data = cache.get_or_set(
        f"dashboard:overview:{rng.key}",
        lambda: metrics.overview(rng),
        dashboard.OVERVIEW_CACHE_SECONDS,
    )
    s = data["sessions"]
    return ok(
        {
            **ctx,
            "sessions": {
                "completed": s["completed"],
                "abandoned": s["abandoned"],
                "today": s["today"],
                "avgPlayers": s["avg_players"],
                "avgDuration": s["avg_duration"],
                "abandonRate": s["abandon_rate"],
            },
            "mostPlayed": data["most_played"],
            "users": data["users"],
            "guestsSeen": data["guests_seen"],
            "active": data["active"],
            "perDay": _per_day(data["per_day"]),
            "live": dashboard.live_rooms(),
            "cachedSeconds": dashboard.OVERVIEW_CACHE_SECONDS,
            "openReports": open_reports(),  # never cached
        }
    )


@staff_api()
def games(request: HttpRequest) -> JsonResponse:
    rng, ctx = _range(request)
    rows = [
        {
            "id": g["id"],
            "name": g["name"],
            "plays": g["plays"],
            "abandoned": g["abandoned"],
            "uniquePlayers": g["unique_players"],
            "avgPlayers": g["avg_players"],
            "avgDuration": g["avg_duration"],
            "completionRate": g["completion_rate"],
        }
        for g in metrics.games_table(rng)
    ]
    return ok({**ctx, "games": rows})


@staff_api()
def game_detail(request: HttpRequest, game_id: str) -> JsonResponse:
    if (
        game_id not in metrics.known_game_ids()
        and not GameSession.objects.filter(game_id=game_id).exists()
    ):
        return fail(404, "NOT_FOUND", "Unknown game.")
    rng, ctx = _range(request)
    game = metrics.game_detail(game_id, rng)
    t = game["totals"]
    return ok(
        {
            **ctx,
            "game": {"id": game["id"], "name": game["name"]},
            "totals": {
                "plays": t["completed"],
                "abandoned": t["abandoned"],
                "uniquePlayers": t["unique_players"],
                "avgPlayers": t["avg_players"],
                "avgDuration": t["avg_duration"],
                "completionRate": t["completion_rate"],
            },
            "perDay": _per_day(game["per_day"]),
            "recent": [
                {
                    "id": s["id"],
                    "status": s["status"],
                    "startedAt": s["started_at"],
                    "durationSeconds": s["duration_seconds"],
                    "playerCount": s["player_count"],
                    "roomCode": s["room_code"],
                }
                for s in game["recent"]
            ],
        }
    )


# ----- Users -------------------------------------------------------------------------


def _user_row(row: dict[str, Any]) -> dict[str, Any]:
    r = people.decorate(row)
    return {
        **_actor(r["row_user_id"], r["row_key"] if r["is_guest"] else "", r["row_nickname"]),
        "username": r["row_username"] or None,
        "firstSeen": r["first_seen"],
        "lastSeen": r["last_seen"],
        "games": r["games"],
        "wins": r["wins"],
        "losses": r["losses"],
        "winRate": r["win_rate"],
        "favorite": _game_ref(r["favorite"]),
    }


@staff_api()
def users(request: HttpRequest) -> JsonResponse:
    search = request.GET.get("q", "").strip()[:50]
    kind = request.GET.get("type", "")
    kind = kind if kind in ("registered", "guest") else ""
    sort = request.GET.get("sort", people.DEFAULT_SORT)
    sort = sort if sort in people.SORTS else people.DEFAULT_SORT
    desc = request.GET.get("dir", "desc") != "asc"
    page, meta = _page(request, people.user_rows(search, kind, sort, desc))
    return ok(
        {
            **meta,
            "query": {"q": search, "type": kind, "sort": sort, "dir": "desc" if desc else "asc"},
            "sorts": list(people.SORTS),
            "minGamesForRates": DASHBOARD_MIN_GAMES_FOR_RATES,
            "results": [_user_row(r) for r in page.object_list],
        }
    )


def _detail_payload(
    request: HttpRequest, actor: people.Actor, user: User | None, detail: dict[str, Any]
) -> JsonResponse:
    t = detail["totals"]
    model_admin = admin.site._registry[User]
    profile = getattr(user, "profile", None) if user else None

    def game(g: dict[str, Any] | None) -> dict[str, Any] | None:
        return {"id": g["id"], "name": g["name"]} if g else None

    return ok(
        {
            "actor": {
                **_actor(
                    user.pk if user else None,
                    actor.guest_key,
                    profile.nickname if profile else (user.username if user else t["nickname"]),
                ),
                "username": user.username if user else None,
                "joined": user.date_joined if user else None,
                "isActive": user.is_active if user else None,
            },
            "permissions": {
                "change": bool(user and model_admin.has_change_permission(request, user)),
                "delete": bool(user and model_admin.has_delete_permission(request, user)),
            },
            "reportsAgainst": reports_against(user, actor.guest_key),
            "minGamesForRates": DASHBOARD_MIN_GAMES_FOR_RATES,
            "totals": {
                "games": t["games"],
                "wins": t["wins"],
                "losses": t["losses"],
                "abandoned": t["abandoned"],
                "winRate": t["win_rate"],
                "firstGame": t["first"],
                "lastGame": t["last"],
            },
            "perGame": [
                {
                    "id": g["id"],
                    "name": g["name"],
                    "played": g["played"],
                    "wins": g["wins"],
                    "losses": g["losses"],
                    "winRate": g["win_rate"],
                    "avgPlacement": g["avg_placement"],
                }
                for g in detail["per_game"]
            ],
            "mostPlayed": game(detail["most_played"]),
            "mostWon": game(detail["most_won"]),
            "mostLost": game(detail["most_lost"]),
            "recent": [
                {
                    "startedAt": p.session.started_at,
                    "game": _game_ref(p.session.game_id),
                    "status": p.session.status,
                    "placement": p.placement,
                    "leftEarly": p.left_early,
                    "opponents": p.opponents,
                }
                for p in detail["recent"]
            ],
            "coPlayers": [
                {
                    **_actor(c["user"], c["guest_key"], c["name"]),
                    "shared": c["shared"],
                    "ahead": c["ahead"],
                    "behind": c["behind"],
                }
                for c in detail["co_players"]
            ],
            "events": [
                {
                    "id": e.pk,
                    "kind": e.kind,
                    "label": e.get_kind_display(),
                    "occurredAt": e.occurred_at,
                    "roomCode": e.room_code,
                    "game": _game_ref(e.game_id),
                }
                for e in detail["events"]
            ],
        }
    )


@staff_api()
def registered_detail(request: HttpRequest, user_id: int) -> JsonResponse:
    user = User.objects.select_related("profile").filter(pk=user_id).first()
    if user is None:
        return fail(404, "NOT_FOUND", "No such account.")
    actor = people.Actor("registered", user, "")
    return _detail_payload(request, actor, user, people.actor_detail(actor))


@staff_api()
def guest_detail(request: HttpRequest, key: str) -> JsonResponse:
    actor = people.Actor("guest", None, key)
    detail = people.actor_detail(actor)
    if not detail["totals"]["first"] and not detail["events"]:
        return fail(404, "NOT_FOUND", "Unknown guest.")
    return _detail_payload(request, actor, None, detail)


@staff_api("POST")
def user_action(request: HttpRequest, user_id: int, action: str) -> JsonResponse:
    """disable / enable / delete one account (the same helpers and LogEntry as the admin)."""
    user = User.objects.filter(pk=user_id).first()
    if user is None:
        return fail(404, "NOT_FOUND", "No such account.")
    model_admin = admin.site._registry[User]
    users_qs = User.objects.filter(pk=user.pk)
    if action == "delete":
        if not model_admin.has_delete_permission(request, user):
            return fail(403, "FORBIDDEN", "You may not delete accounts.")
        accounts_admin.delete_accounts(request, model_admin, users_qs)
        return ok({"ok": True, "deleted": True})
    if action in ("disable", "enable"):
        if not model_admin.has_change_permission(request, user):
            return fail(403, "FORBIDDEN", "You may not change accounts.")
        accounts_admin.set_active(request, model_admin, users_qs, action == "enable")
        user.refresh_from_db()
        return ok({"ok": True, "isActive": user.is_active})
    return fail(404, "NOT_FOUND", "Unknown action.")


# ----- Leaderboards and activity -----------------------------------------------------


@staff_api()
def leaderboards(request: HttpRequest) -> JsonResponse:
    game_id = request.GET.get("game") or None
    if game_id and game_id not in metrics.known_game_ids():
        game_id = None
    boards = people.leaderboards(game_id)

    def rows(key: str) -> list[dict[str, Any]]:
        return [
            {
                **_actor(r["user"], r["guest_key"], r["name"]),
                "games": r["games"],
                "wins": r["wins"],
                "winRate": r.get("win_rate"),
            }
            for r in boards[key]
        ]

    return ok(
        {
            "game": _game_ref(game_id),
            "games": _games_list(),
            "minGamesForRates": DASHBOARD_MIN_GAMES_FOR_RATES,
            "mostWins": rows("most_wins"),
            "bestRate": rows("best_rate"),
            "mostGames": rows("most_games"),
        }
    )


@staff_api()
def activity(request: HttpRequest) -> JsonResponse:
    events = ActivityEvent.objects.select_related("user__profile").order_by("-occurred_at", "-id")
    kind = request.GET.get("kind", "")
    kind = kind if kind in ActivityEvent.Kind.values else ""
    if kind:
        events = events.filter(kind=kind)
    game_id = request.GET.get("game", "")
    if game_id:
        events = events.filter(game_id=game_id)
    day = parse_date(request.GET.get("date") or "") if request.GET.get("date") else None
    if day:
        tz = timezone.get_current_timezone()
        start = timezone.make_aware(datetime.combine(day, datetime.min.time()), tz)
        end = timezone.make_aware(datetime.combine(day, datetime.max.time()), tz)
        events = events.filter(occurred_at__range=(start, end))
    page, meta = _page(request, events)

    def who(e: ActivityEvent) -> dict[str, Any] | None:
        if e.user_id:
            profile = getattr(e.user, "profile", None)
            return _actor(e.user_id, "", profile.nickname if profile else e.user.username)
        if e.guest_key:
            return _actor(None, e.guest_key, f"guest {e.guest_key[:8]}")
        return None

    return ok(
        {
            **meta,
            "query": {"kind": kind, "game": game_id, "date": day},
            "kinds": [{"value": v, "label": label} for v, label in ActivityEvent.Kind.choices],
            "games": _games_list(),
            "results": [
                {
                    "id": e.pk,
                    "kind": e.kind,
                    "label": e.get_kind_display(),
                    "occurredAt": e.occurred_at,
                    "who": who(e),
                    "roomCode": e.room_code,
                    "game": _game_ref(e.game_id),
                }
                for e in page.object_list
            ],
        }
    )


# ----- Reports -----------------------------------------------------------------------


def open_reports() -> int:
    return Report.objects.filter(status=Report.Status.OPEN).count()


def reports_against(user: User | None, guest_key: str) -> dict[str, int]:
    """{total, open} reports about a registered account or a guest key."""
    who = Q(reported_user=user) if user is not None else Q(reported_guest_key=guest_key)
    rows = Report.objects.filter(who, ~Q(reported_guest_key="") | Q(reported_user__isnull=False))
    return {
        "total": rows.count(),
        "open": rows.filter(status=Report.Status.OPEN).count(),
    }


def _no_store(response: JsonResponse) -> JsonResponse:
    response["Cache-Control"] = "no-store"
    return response


def _report_person(user: User | None, nickname: str) -> dict[str, Any]:
    profile = getattr(user, "profile", None) if user else None
    return {
        **_actor(user.pk if user else None, "", nickname),
        "nickname": nickname,
        "tag": profile.tag if profile else None,
        "username": user.username if user else None,
    }


def _reported(r: Report) -> dict[str, Any]:
    if r.reported_user is not None:
        return _report_person(r.reported_user, r.reported_nickname)
    if r.reported_guest_key:
        return {
            **_actor(None, r.reported_guest_key, r.reported_nickname),
            "nickname": r.reported_nickname,
            "tag": None,
            "username": None,
        }
    # the reported account was deleted since: only the nickname snapshot is left
    return {
        "kind": "deleted",
        "userId": None,
        "guestKey": None,
        "name": r.reported_nickname,
        "nickname": r.reported_nickname,
        "tag": None,
        "username": None,
    }


def _report_row(r: Report) -> dict[str, Any]:
    reporter = r.reporter
    return {
        "id": r.pk,
        "createdAt": r.created_at,
        "status": r.status,
        "reason": r.reason,
        "note": r.note,
        "reporter": _report_person(reporter, reporter.profile.nickname)
        if reporter is not None and hasattr(reporter, "profile")
        else None,
        "reported": _reported(r),
        "roomCode": r.room_code or None,
        "gameId": r.game_id or None,
        "game": _game_ref(r.game_id or None),
        "resolvedBy": r.resolved_by.get_username() if r.resolved_by else None,
        "resolvedNote": r.resolved_note,
        "resolvedAt": r.resolved_at,
    }


@staff_api()
def reports(request: HttpRequest) -> JsonResponse:
    """Open reports first, then newest first; filters ?status= and ?reason=."""
    status = request.GET.get("status", "")
    status = status if status in Report.Status.values else ""
    reason = request.GET.get("reason", "")
    reason = reason if reason in REPORT_REASONS else ""
    rows = Report.objects.select_related(
        "reporter__profile", "reported_user__profile", "resolved_by"
    ).annotate(
        open_first=Case(
            When(status=Report.Status.OPEN, then=Value(0)),
            default=Value(1),
            output_field=IntegerField(),
        )
    )
    if status:
        rows = rows.filter(status=status)
    if reason:
        rows = rows.filter(reason=reason)
    page, meta = _page(request, rows.order_by("open_first", "-created_at", "-id"))
    return _no_store(
        ok(
            {
                **meta,
                "query": {"status": status, "reason": reason},
                "statuses": list(Report.Status.values),
                "reasons": list(REPORT_REASONS),
                "openReports": open_reports(),
                "results": [_report_row(r) for r in page.object_list],
            }
        )
    )


@staff_api("POST")
def resolve_report(request: HttpRequest, report_id: int) -> JsonResponse:
    """{action: "resolved" | "dismissed", note?}: close an open report (audit-logged)."""
    report = Report.objects.filter(pk=report_id).first()
    if report is None:
        return _no_store(fail(404, "NOT_FOUND", "No such report."))
    model_admin = admin.site._registry[Report]
    if not model_admin.has_change_permission(request, report):
        return _no_store(fail(403, "FORBIDDEN", "You may not handle reports."))
    try:
        body = json.loads(request.body or b"{}")
    except ValueError:
        body = None
    action = body.get("action") if isinstance(body, dict) else None
    if action not in (Report.Status.RESOLVED, Report.Status.DISMISSED):
        return _no_store(fail(400, "INVALID_INPUT", "Choose resolved or dismissed."))
    try:
        note = clean_note(body.get("note"))
    except SocialError as exc:
        return _no_store(fail(400, "INVALID_INPUT", exc.message))
    if len(note) > RESOLVED_NOTE_MAX:
        return _no_store(fail(400, "INVALID_INPUT", "The note is too long."))
    if report.status != Report.Status.OPEN:
        return _no_store(fail(409, "NOT_OPEN", "This report was already handled."))
    report.status, report.resolved_note = action, note
    report.resolved_by, report.resolved_at = request.user, timezone.now()
    report.save(update_fields=["status", "resolved_note", "resolved_by", "resolved_at"])
    verb = "Resolved" if action == Report.Status.RESOLVED else "Dismissed"
    model_admin.log_change(request, report, f"{verb} report" + (f": {note}" if note else ""))
    report = Report.objects.select_related(
        "reporter__profile", "reported_user__profile", "resolved_by"
    ).get(pk=report.pk)
    return _no_store(ok({"ok": True, "report": _report_row(report), "openReports": open_reports()}))
