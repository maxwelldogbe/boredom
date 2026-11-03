"""Player Nemesis and wallet API (Bearer token, registered accounts, Cache-Control: no-store).

While NEMESIS_ENABLED is off only GET /api/nemesis/status answers ({enabled: false}); every
other route is 404. Nothing here is ever sent over the room WebSocket.
"""

import json
from collections.abc import Callable
from functools import wraps
from typing import Any

from django.conf import settings
from django.contrib.auth.models import User
from django.core.cache import cache
from django.db.models import Q
from django.http import HttpRequest, JsonResponse
from django.views.decorators.csrf import csrf_exempt

from accounts.me import iso
from accounts.ratelimit import KeyedRateLimiter
from accounts.views import ApiError, _bearer_user, api
from games.constants import WALLET_PAGE_SIZE
from nemesis import ids, services
from nemesis import wallet as money
from nemesis.errors import NemesisError
from nemesis.models import LedgerAccount, LedgerEntry, LedgerTransaction

Kind = LedgerAccount.Kind
TxKind = LedgerTransaction.Kind
ID_UPLOADS_PER_HOUR = 5
id_upload_limiter = KeyedRateLimiter(limit=ID_UPLOADS_PER_HOUR, window=3600.0)
password_limiter = KeyedRateLimiter()
IDEMPOTENCY_TTL_S = 24 * 60 * 60
IDEMPOTENCY_KEY_MAX = 100


def _error(exc: NemesisError) -> JsonResponse:
    return JsonResponse(exc.payload(), status=exc.status)


def _not_found() -> JsonResponse:
    return JsonResponse({"error": {"code": "NOT_FOUND", "message": "Not found."}}, status=404)


def _replayed(request: HttpRequest, user: User, run: Callable[[], JsonResponse]) -> JsonResponse:
    """Honour an Idempotency-Key header: a repeated key gets the first successful response."""
    key = request.headers.get("Idempotency-Key", "")
    if not key or len(key) > IDEMPOTENCY_KEY_MAX:
        return run()
    cache_key = f"nemesis-idem:{user.pk}:{request.method}:{request.path}:{key}"
    saved = cache.get(cache_key)
    if saved is not None:
        return JsonResponse(saved[1], status=saved[0])
    response = run()
    if 200 <= response.status_code < 300:
        cache.set(
            cache_key, (response.status_code, json.loads(response.content)), IDEMPOTENCY_TTL_S
        )
    return response


def nemesis_api(method: str) -> Callable[..., Callable[..., JsonResponse]]:
    """`api(method, auth=True, no_store=True)`, 404 while disabled, NemesisError rendered.

    POST views accept an Idempotency-Key header (see _replayed).
    """

    def decorate(view: Callable[..., JsonResponse]) -> Callable[..., JsonResponse]:
        @wraps(view)
        def inner(request: HttpRequest, body: dict[str, Any], user: User | None, **kw: Any):
            assert user is not None
            if not settings.NEMESIS_ENABLED:
                return _not_found()

            def run() -> JsonResponse:
                try:
                    return view(request, body, user, **kw)
                except NemesisError as exc:
                    return _error(exc)

            return _replayed(request, user, run) if method == "POST" else run()

        return api(method, auth=True, no_store=True)(inner)

    return decorate


@api("GET", auth=True, no_store=True)
def status(request: HttpRequest, body: dict[str, Any], user: User) -> JsonResponse:
    if not settings.NEMESIS_ENABLED:
        return JsonResponse({"enabled": False})
    return JsonResponse(services.status(user))


@csrf_exempt
def submit_id(request: HttpRequest) -> JsonResponse:
    """POST multipart {idType, fullName, idNumber, dob, front, back?}: one ID submission."""
    try:
        if request.method != "POST":
            response = ApiError(405, "METHOD_NOT_ALLOWED", "Use POST.").response()
        elif not settings.NEMESIS_ENABLED:
            response = _not_found()
        else:
            user = _bearer_user(request)
            if not id_upload_limiter.allow(str(user.pk)):
                raise NemesisError("RATE_LIMITED", "Too many uploads. Try again later.")
            ids.submit(user, request.POST, request.FILES)
            response = JsonResponse(services.status(user), status=201)
    except ApiError as exc:
        response = exc.response()
    except NemesisError as exc:
        response = _error(exc)
    response["Cache-Control"] = "no-store"
    return response


@nemesis_api("POST")
def activate(request: HttpRequest, body: dict[str, Any], user: User) -> JsonResponse:
    return JsonResponse(services.activate(user, body))


@nemesis_api("POST")
def deactivate(request: HttpRequest, body: dict[str, Any], user: User) -> JsonResponse:
    return JsonResponse(services.deactivate(user))


@nemesis_api("GET")
def wallet(request: HttpRequest, body: dict[str, Any], user: User) -> JsonResponse:
    return JsonResponse(services.wallet(user))


def _cursor(raw: str | None) -> int | None:
    if raw in (None, ""):
        return None
    try:
        value = int(raw)
    except ValueError:
        raise NemesisError("INVALID_INPUT", "Bad cursor.") from None
    if value < 1:
        raise NemesisError("INVALID_INPUT", "Bad cursor.")
    return value


@nemesis_api("GET")
def entries(request: HttpRequest, body: dict[str, Any], user: User) -> JsonResponse:
    """The player's ledger lines, newest first, WALLET_PAGE_SIZE per page (?cursor=<id>).

    Lines on the available balance, plus the payout line of the held balance
    (withdrawal_paid), which is the only one that never touches the available balance.
    """
    cursor = _cursor(request.GET.get("cursor"))
    rows = LedgerEntry.objects.filter(
        Q(account__user=user, account__kind=Kind.USER)
        | Q(
            account__user=user,
            account__kind=Kind.WITHDRAWAL_HOLD,
            transaction__kind=TxKind.WITHDRAWAL_PAID,
        )
    ).select_related("transaction", "account")
    if cursor is not None:
        rows = rows.filter(pk__lt=cursor)
    page = list(rows.order_by("-pk")[: WALLET_PAGE_SIZE + 1])
    more = len(page) > WALLET_PAGE_SIZE
    page = page[:WALLET_PAGE_SIZE]
    return JsonResponse(
        {
            "entries": [
                {
                    "id": e.pk,
                    "kind": e.transaction.kind,
                    "amount": e.amount,
                    "balanceAfter": e.balance_after,
                    "account": "held" if e.account.kind == Kind.WITHDRAWAL_HOLD else "available",
                    "createdAt": iso(e.created_at),
                }
                for e in page
            ],
            "nextCursor": page[-1].pk if more else None,
        }
    )


# ----- deposits, withdrawals, limits, exclusion ------------------------------------------


@nemesis_api("GET")
def payment_details(request: HttpRequest, body: dict[str, Any], user: User) -> JsonResponse:
    return JsonResponse(money.payment_details(user))


@nemesis_api("GET")
def deposits(request: HttpRequest, body: dict[str, Any], user: User) -> JsonResponse:
    return JsonResponse(money.deposits(user))


@nemesis_api("POST")
def create_deposit(request: HttpRequest, body: dict[str, Any], user: User) -> JsonResponse:
    return JsonResponse(money.create_deposit(user, body), status=201)


@nemesis_api("POST")
def submit_deposit(
    request: HttpRequest, body: dict[str, Any], user: User, deposit_id: int
) -> JsonResponse:
    return JsonResponse(money.submit_deposit(user, deposit_id, body))


@nemesis_api("POST")
def cancel_deposit(
    request: HttpRequest, body: dict[str, Any], user: User, deposit_id: int
) -> JsonResponse:
    return JsonResponse(money.cancel_deposit(user, deposit_id))


@nemesis_api("POST")
def payout_destination(request: HttpRequest, body: dict[str, Any], user: User) -> JsonResponse:
    if not password_limiter.allow(str(user.pk)):
        raise NemesisError("RATE_LIMITED", "Too many attempts. Wait a minute.")
    return JsonResponse(money.set_payout(user, body))


@nemesis_api("GET")
def withdrawals(request: HttpRequest, body: dict[str, Any], user: User) -> JsonResponse:
    return JsonResponse(money.withdrawals(user))


@nemesis_api("POST")
def create_withdrawal(request: HttpRequest, body: dict[str, Any], user: User) -> JsonResponse:
    return JsonResponse(money.create_withdrawal(user, body), status=201)


@nemesis_api("POST")
def cancel_withdrawal(
    request: HttpRequest, body: dict[str, Any], user: User, withdrawal_id: int
) -> JsonResponse:
    return JsonResponse(money.cancel_withdrawal(user, withdrawal_id))


@nemesis_api("PUT")
def limits(request: HttpRequest, body: dict[str, Any], user: User) -> JsonResponse:
    return JsonResponse(money.set_limits(user, body))


@nemesis_api("POST")
def exclude(request: HttpRequest, body: dict[str, Any], user: User) -> JsonResponse:
    return JsonResponse({"exclusion": money.exclude(user, body)})
