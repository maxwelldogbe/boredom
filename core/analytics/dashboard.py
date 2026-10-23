"""Dashboard pages inside the admin site. Every view here is wrapped by `admin_view`
(staff only) in BoredomAdminSite.get_urls.

No page shows passwords, tokens, raw profile ids, seat ids or IP addresses.
"""

import csv
from collections.abc import Iterator
from datetime import datetime, time
from typing import Any

from django.conf import settings
from django.contrib import admin, messages
from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.http import Http404, HttpRequest, HttpResponse, StreamingHttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.template.response import TemplateResponse
from django.urls import path
from django.utils import timezone
from django.utils.dateparse import parse_date

from accounts import admin as accounts_admin
from analytics import metrics, people
from analytics.models import ActivityEvent, GameSession
from games.constants import (
    ACTIVITY_RETENTION_DAYS,
    DASHBOARD_MIN_GAMES_FOR_RATES,
    DASHBOARD_PAGE_SIZE,
)

OVERVIEW_CACHE_SECONDS = 60


def urls(site: admin.AdminSite) -> list:
    def page(route: str, view, name: str):
        return path(route, site.admin_view(view), name=name)

    return [
        page("dashboard/games/", games, "dashboard-games"),
        page("dashboard/games/<slug:game_id>/", game_detail, "dashboard-game"),
        page("dashboard/users/", users, "dashboard-users"),
        page("dashboard/users/u/<int:user_id>/", registered_detail, "dashboard-user"),
        page("dashboard/users/g/<slug:key>/", guest_detail, "dashboard-guest"),
        page(
            "dashboard/users/u/<int:user_id>/<slug:action>/", user_action, "dashboard-user-action"
        ),
        page("dashboard/leaderboards/", leaderboards, "dashboard-leaderboards"),
        page("dashboard/activity/", activity, "dashboard-activity"),
        page("dashboard/data/", data, "dashboard-data"),
        page("dashboard/export/users.csv", export_users, "dashboard-export-users"),
        page("dashboard/export/sessions.csv", export_sessions, "dashboard-export-sessions"),
    ]


def render(request: HttpRequest, template: str, section: str, title: str, **context: Any):
    ctx = {
        **admin.site.each_context(request),
        "title": title,
        "dash_page": section,
        "time_zone": settings.TIME_ZONE,
        "min_games": DASHBOARD_MIN_GAMES_FOR_RATES,
        "retention_days": ACTIVITY_RETENTION_DAYS,
        **context,
    }
    return TemplateResponse(request, f"admin/dashboard/{template}", ctx)


def _query(request: HttpRequest) -> str:
    """The current filters as a query string, without `page` (for pager links)."""
    params = request.GET.copy()
    params.pop("page", None)
    return params.urlencode()


def _range(request: HttpRequest) -> dict[str, Any]:
    return {"rng": metrics.parse_range(request.GET.get("range")), "ranges": metrics.RANGES}


# ----- Overview and Games --------------------------------------------------------------


def live_rooms() -> list[dict[str, Any]]:
    """A read-only snapshot of the in-memory rooms: code, status, game and player counts."""
    from rooms import manager as manager_module

    snapshot = []
    for room in list(manager_module.manager.rooms.values()):
        seated = room.seated()
        game = room.game_id or room.selected_game
        snapshot.append(
            {
                "code": room.code,
                "status": room.status,
                "game": metrics.game_name(game) if game else "—",
                "players": len(seated),
                "online": sum(1 for p in seated if p.online),
            }
        )
    return sorted(snapshot, key=lambda r: (r["status"] != "playing", r["code"]))


def overview(request: HttpRequest, site: admin.AdminSite | None = None) -> HttpResponse:
    ctx = _range(request)
    rng = ctx["rng"]
    data = cache.get_or_set(
        f"dashboard:overview:{rng.key}", lambda: metrics.overview(rng), OVERVIEW_CACHE_SECONDS
    )
    live = live_rooms()
    return render(
        request,
        "overview.html",
        "overview",
        "Overview",
        data=data,
        live=live,
        live_players=sum(r["players"] for r in live),
        **ctx,
    )


def games(request: HttpRequest) -> HttpResponse:
    ctx = _range(request)
    return render(
        request, "games.html", "games", "Games", games=metrics.games_table(ctx["rng"]), **ctx
    )


def game_detail(request: HttpRequest, game_id: str) -> HttpResponse:
    if (
        game_id not in metrics.known_game_ids()
        and not GameSession.objects.filter(game_id=game_id).exists()
    ):
        raise Http404("Unknown game.")
    ctx = _range(request)
    game = metrics.game_detail(game_id, ctx["rng"])
    peak = max((n for _, n in game["per_day"]), default=0)
    return render(request, "game_detail.html", "games", game["name"], game=game, peak=peak, **ctx)


# ----- Users ---------------------------------------------------------------------------


def users(request: HttpRequest) -> HttpResponse:
    search = request.GET.get("q", "").strip()[:50]
    kind = request.GET.get("type", "")
    kind = kind if kind in ("registered", "guest") else ""
    sort = request.GET.get("sort", people.DEFAULT_SORT)
    sort = sort if sort in people.SORTS else people.DEFAULT_SORT
    desc = request.GET.get("dir", "desc") != "asc"
    rows = people.user_rows(search, kind, sort, desc)
    page = Paginator(rows, DASHBOARD_PAGE_SIZE).get_page(request.GET.get("page"))
    page.object_list = [people.decorate(r) for r in page.object_list]
    return render(
        request,
        "users.html",
        "users",
        "Users",
        page=page,
        query=_query(request),
        search=search,
        kind=kind,
        sort=sort,
        desc=desc,
        sorts=people.SORTS,
    )


def registered_detail(request: HttpRequest, user_id: int) -> HttpResponse:
    user = get_object_or_404(User.objects.select_related("profile"), pk=user_id)
    actor = people.Actor("registered", user, "")
    name = getattr(getattr(user, "profile", None), "nickname", user.username)
    return render(
        request,
        "user_detail.html",
        "users",
        name,
        actor=actor,
        account=user,
        detail=people.actor_detail(actor),
    )


def guest_detail(request: HttpRequest, key: str) -> HttpResponse:
    actor = people.Actor("guest", None, key)
    detail = people.actor_detail(actor)
    if not detail["totals"]["first"] and not detail["events"]:
        raise Http404("Unknown guest.")
    title = f"{detail['totals']['nickname'] or 'Guest'} (guest {key[:8]})"
    return render(request, "user_detail.html", "users", title, actor=actor, detail=detail)


def user_action(request: HttpRequest, user_id: int, action: str) -> HttpResponse:
    """Disable / enable (POST) and delete (GET confirms, POST deletes) one account."""
    user = get_object_or_404(User, pk=user_id)
    if action not in ("disable", "enable", "delete"):
        raise Http404("Unknown action.")
    detail_url = redirect("admin:dashboard-user", user_id=user_id)
    if action == "delete" and request.method != "POST":
        return render(request, "delete_confirm.html", "users", "Delete account", account=user)
    if request.method != "POST":
        return detail_url
    model_admin = admin.site._registry[User]
    if action == "delete":
        if not model_admin.has_delete_permission(request, user):
            raise Http404("Not allowed.")
        accounts_admin.delete_accounts(request, model_admin, User.objects.filter(pk=user.pk))
        messages.success(request, "Account deleted. Its games are kept as “Deleted player”.")
        return redirect("admin:dashboard-users")
    if not model_admin.has_change_permission(request, user):
        raise Http404("Not allowed.")
    accounts_admin.set_active(
        request, model_admin, User.objects.filter(pk=user.pk), action == "enable"
    )
    messages.success(request, f"Account {'enabled' if action == 'enable' else 'disabled'}.")
    return detail_url


# ----- Leaderboards and activity -------------------------------------------------------


def leaderboards(request: HttpRequest) -> HttpResponse:
    game_id = request.GET.get("game") or None
    if game_id and game_id not in metrics.known_game_ids():
        game_id = None
    boards = people.leaderboards(game_id)
    games_list = [(g, metrics.game_name(g)) for g in metrics.known_game_ids()]
    title = f"Leaderboards: {metrics.game_name(game_id)}" if game_id else "Leaderboards"
    return render(
        request,
        "leaderboards.html",
        "leaderboards",
        title,
        board_list=[
            ("Most wins", boards["most_wins"], "Wins"),
            ("Best win rate", boards["best_rate"], "Win rate"),
            ("Most games played", boards["most_games"], "Games"),
        ],
        game_id=game_id,
        games_list=games_list,
    )


def activity(request: HttpRequest) -> HttpResponse:
    events = ActivityEvent.objects.select_related("user__profile").order_by("-occurred_at", "-id")
    kind = request.GET.get("kind", "")
    if kind in ActivityEvent.Kind.values:
        events = events.filter(kind=kind)
    else:
        kind = ""
    game_id = request.GET.get("game", "")
    if game_id:
        events = events.filter(game_id=game_id)
    day = parse_date(request.GET.get("date", "") or "") if request.GET.get("date") else None
    if day:
        tz = timezone.get_current_timezone()
        start = timezone.make_aware(datetime.combine(day, time.min), tz)
        end = timezone.make_aware(datetime.combine(day, time.max), tz)
        events = events.filter(occurred_at__range=(start, end))
    page = Paginator(events, DASHBOARD_PAGE_SIZE).get_page(request.GET.get("page"))
    return render(
        request,
        "activity.html",
        "activity",
        "Activity",
        page=page,
        query=_query(request),
        kind=kind,
        kinds=ActivityEvent.Kind.choices,
        game_id=game_id,
        games_list=[(g, metrics.game_name(g)) for g in metrics.known_game_ids()],
        day=day,
    )


def data(request: HttpRequest) -> HttpResponse:
    """Django's model list (the stock admin index)."""
    context = {
        **admin.site.each_context(request),
        "title": "Data",
        "subtitle": None,
        "app_list": admin.site.get_app_list(request),
        "dash_page": "data",
    }
    return TemplateResponse(request, "admin/index.html", context)


# ----- CSV export ----------------------------------------------------------------------


class _Echo:
    def write(self, value: str) -> str:
        return value


def _csv_response(filename: str, header: list[str], rows: Iterator[list[Any]]):
    writer = csv.writer(_Echo())

    def stream() -> Iterator[str]:
        yield writer.writerow(header)
        for row in rows:
            yield writer.writerow(row)

    response = StreamingHttpResponse(stream(), content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


def _iso(value: datetime | None) -> str:
    return value.isoformat() if value else ""


def export_users(request: HttpRequest) -> StreamingHttpResponse:
    header = [
        "type",
        "key",
        "username",
        "nickname",
        "first_seen",
        "last_seen",
        "games",
        "wins",
        "losses",
        "win_rate",
        "favorite_game",
    ]

    def rows() -> Iterator[list[Any]]:
        for raw in people.user_rows(sort="games").iterator(chunk_size=500):
            r = people.decorate(raw)
            rate = r["win_rate"]
            yield [
                r["row_kind"],
                r["short_key"] if r["is_guest"] else r["row_key"],
                r["row_username"],
                r["row_nickname"] or "",
                _iso(r["first_seen"]),
                _iso(r["last_seen"]),
                r["games"],
                r["wins"],
                r["losses"],
                f"{rate:.4f}" if rate is not None else "",
                r["favorite"] or "",
            ]

    return _csv_response("boredom-users.csv", header, rows())


def export_sessions(request: HttpRequest) -> StreamingHttpResponse:
    header = [
        "id",
        "game_id",
        "status",
        "started_at",
        "ended_at",
        "duration_seconds",
        "player_count",
        "registered_players",
        "guest_players",
        "winners",
        "left_early",
    ]
    sessions = (
        GameSession.objects.order_by("started_at", "id")
        .annotate(
            registered=Count("participations", filter=Q(participations__player_type="registered")),
            guests=Count("participations", filter=Q(participations__player_type="guest")),
            winners=Count("participations", filter=Q(participations__is_win=True)),
            left=Count("participations", filter=Q(participations__left_early=True)),
        )
        .values_list(
            "id",
            "game_id",
            "status",
            "started_at",
            "ended_at",
            "duration_seconds",
            "player_count",
            "registered",
            "guests",
            "winners",
            "left",
        )
    )

    def rows() -> Iterator[list[Any]]:
        for row in sessions.iterator(chunk_size=500):
            values = list(row)
            values[3], values[4] = _iso(values[3]), _iso(values[4])
            yield values

    return _csv_response("boredom-sessions.csv", header, rows())
