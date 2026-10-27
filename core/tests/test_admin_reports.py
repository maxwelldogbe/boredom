"""Staff reports API: access, CSRF, filters and ordering, resolve and dismiss, counts."""

import json
from datetime import timedelta

import pytest
from django.contrib.admin.models import LogEntry
from django.contrib.auth.models import Permission, User
from django.test import Client
from django.utils import timezone

from accounts import services as account_services
from accounts.tokens import issue_token
from social.models import Report
from tests.dashboard_data import GUEST_CARL, account
from tests.test_admin_api import _csrf, get, staff

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("fresh_state")]

A = "/api/admin/"


def report(
    reporter: User | None,
    *,
    user=None,
    guest="",
    nickname="Target",
    reason="spam",
    status="open",
    hours_ago: float = 0,
    note="",
    room="ABCD",
    game="rps",
) -> Report:
    r = Report.objects.create(
        reporter=reporter,
        reported_user=user,
        reported_guest_key=guest,
        reported_nickname=nickname,
        reason=reason,
        note=note,
        room_code=room,
        game_id=game,
        status=status,
    )
    Report.objects.filter(pk=r.pk).update(created_at=timezone.now() - timedelta(hours=hours_ago))
    return Report.objects.get(pk=r.pk)


@pytest.fixture
def people() -> dict[str, User]:
    return {
        "ann": account("ann_login", "Ann"),
        "bob": account("bob_login", "Bob"),
    }


def resolve(client: Client, report_id: int, body, csrf: bool = True):
    headers = {"HTTP_X_CSRFTOKEN": _csrf(client)} if csrf else {}
    return client.post(
        A + f"reports/{report_id}/resolve",
        data=json.dumps(body),
        content_type="application/json",
        **headers,
    )


def test_reports_require_staff(people) -> None:
    r = report(people["ann"], user=people["bob"])
    player = Client(HTTP_HOST="localhost")
    player.force_login(people["ann"])
    for client in (Client(HTTP_HOST="localhost"), player):
        assert client.get(A + "reports").status_code in (401, 403)
        assert client.post(A + f"reports/{r.pk}/resolve").status_code in (401, 403)
    assert Report.objects.get().status == "open"


def test_list_shape_and_no_store(people) -> None:
    ann, bob = people["ann"], people["bob"]
    report(ann, user=bob, nickname="Bob", reason="harassment", note="mean words")
    response = staff().get(A + "reports")
    assert response["Cache-Control"] == "no-store"
    data = response.json()
    assert data["count"] == 1 and data["openReports"] == 1 and data["page"] == 1
    assert data["reasons"] == [
        "harassment",
        "inappropriate_name_or_avatar",
        "cheating",
        "spam",
        "other",
    ]
    assert data["statuses"] == ["open", "resolved", "dismissed"]
    row = data["results"][0]
    assert set(row) == {
        "id",
        "createdAt",
        "status",
        "reason",
        "note",
        "reporter",
        "reported",
        "roomCode",
        "gameId",
        "game",
        "resolvedBy",
        "resolvedNote",
        "resolvedAt",
    }
    assert row["note"] == "mean words" and row["roomCode"] == "ABCD" and row["gameId"] == "rps"
    assert row["game"]["id"] == "rps" and row["resolvedBy"] is None
    assert row["reporter"] == {
        "kind": "registered",
        "userId": ann.pk,
        "guestKey": None,
        "name": "Ann",
        "nickname": "Ann",
        "tag": ann.profile.tag,
        "username": "ann_login",
    }
    assert row["reported"]["kind"] == "registered" and row["reported"]["username"] == "bob_login"
    assert row["reported"]["tag"] == bob.profile.tag and row["reported"]["userId"] == bob.pk


def test_guest_and_deleted_targets(people) -> None:
    ann, bob = people["ann"], people["bob"]
    report(ann, guest=GUEST_CARL, nickname="Carl", room="WXYZ", game="hangman")
    report(bob, user=ann, nickname="Ann")
    account_services.delete_account(ann)
    rows = get(staff(), "reports")["results"]
    by_nick = {r["reported"]["nickname"]: r for r in rows}
    carl = by_nick["Carl"]
    assert carl["reported"]["kind"] == "guest" and carl["reported"]["guestKey"] == GUEST_CARL
    assert carl["reported"]["username"] is None and carl["reported"]["tag"] is None
    assert carl["reporter"] is None  # ann was deleted
    gone = by_nick["Ann"]
    assert gone["reported"]["kind"] == "deleted" and gone["reported"]["userId"] is None
    assert gone["reporter"]["username"] == "bob_login"


def test_open_first_then_newest_and_filters(people) -> None:
    ann, bob = people["ann"], people["bob"]
    old_open = report(ann, user=bob, hours_ago=10)
    new_done = report(ann, user=bob, status="resolved", hours_ago=1)
    new_open = report(ann, user=bob, reason="cheating", hours_ago=2)
    dismissed = report(bob, user=ann, status="dismissed", hours_ago=0)
    client = staff()
    ids = [r["id"] for r in get(client, "reports")["results"]]
    assert ids == [new_open.pk, old_open.pk, dismissed.pk, new_done.pk]
    assert [r["id"] for r in get(client, "reports?status=open")["results"]] == [
        new_open.pk,
        old_open.pk,
    ]
    assert [r["id"] for r in get(client, "reports?reason=cheating")["results"]] == [new_open.pk]
    assert len(get(client, "reports?status=bogus&reason=bogus")["results"]) == 4
    assert get(client, "reports?status=dismissed")["query"] == {"status": "dismissed", "reason": ""}


def test_pagination(people, monkeypatch) -> None:
    from analytics import api

    monkeypatch.setattr(api, "DASHBOARD_PAGE_SIZE", 2)
    for _ in range(5):
        report(people["ann"], user=people["bob"])
    client = staff()
    first, last = get(client, "reports"), get(client, "reports?page=3")
    assert first["numPages"] == 3 and len(first["results"]) == 2
    assert last["page"] == 3 and len(last["results"]) == 1


def test_resolve_and_dismiss_with_audit(people) -> None:
    ann, bob = people["ann"], people["bob"]
    one, two = report(ann, user=bob), report(bob, user=ann)
    client = staff(csrf=True)
    assert resolve(client, one.pk, {"action": "resolved"}, csrf=False).status_code == 403
    assert client.get(A + f"reports/{one.pk}/resolve").status_code == 405
    response = resolve(client, one.pk, {"action": "resolved", "note": "warned\x00 them"})
    assert response.status_code == 200 and response["Cache-Control"] == "no-store"
    data = response.json()
    assert data["openReports"] == 1 and data["report"]["status"] == "resolved"
    assert (
        data["report"]["resolvedBy"] == "boss" and data["report"]["resolvedNote"] == "warned them"
    )
    assert data["report"]["resolvedAt"]
    assert (
        resolve(client, two.pk, {"action": "dismissed"}).json()["report"]["status"] == "dismissed"
    )
    messages = list(LogEntry.objects.order_by("id").values_list("change_message", flat=True))
    assert messages == ["Resolved report: warned them", "Dismissed report"]
    again = resolve(client, one.pk, {"action": "dismissed"})
    assert again.status_code == 409 and again.json()["error"]["code"] == "NOT_OPEN"


def test_resolve_validation(people) -> None:
    r = report(people["ann"], user=people["bob"])
    client = staff()
    for body in (
        {},
        {"action": "open"},
        {"action": "resolved", "note": 3},
        {"action": "resolved", "note": "x" * 501},
    ):
        response = resolve(client, r.pk, body, csrf=False)
        assert response.status_code == 400, body
    assert resolve(client, 999, {"action": "resolved"}, csrf=False).status_code == 404
    assert Report.objects.get().status == "open"


def test_staff_without_permission_cannot_resolve(people) -> None:
    r = report(people["ann"], user=people["bob"])
    client = staff(superuser=False)
    assert get(client, "reports")["count"] == 1  # reading is fine for any staff
    assert resolve(client, r.pk, {"action": "resolved"}, csrf=False).status_code == 403
    boss = User.objects.get(username="boss")
    boss.user_permissions.add(Permission.objects.get(codename="change_report"))
    client.force_login(User.objects.get(pk=boss.pk))
    assert resolve(client, r.pk, {"action": "resolved"}, csrf=False).status_code == 200


def test_counts_in_overview_session_and_user_detail(people) -> None:
    ann, bob = people["ann"], people["bob"]
    report(ann, user=bob)
    report(ann, user=bob, status="resolved")
    report(bob, user=ann)
    report(ann, guest=GUEST_CARL)
    client = staff()
    assert get(client, "overview")["openReports"] == 3
    assert get(client, "session")["openReports"] == 3
    assert get(Client(HTTP_HOST="localhost"), "session")["openReports"] is None
    assert get(client, f"users/u/{bob.pk}")["reportsAgainst"] == {"total": 2, "open": 1}
    assert get(client, f"users/u/{ann.pk}")["reportsAgainst"] == {"total": 1, "open": 1}
    from tests.dashboard_data import play

    play("rps", [(GUEST_CARL, "Carl", 1), (bob, "Bob", 2)])
    assert get(client, f"users/g/{GUEST_CARL}")["reportsAgainst"] == {"total": 1, "open": 1}


def test_no_secrets(people) -> None:
    ann, bob = people["ann"], people["bob"]
    report(ann, user=bob)
    text = json.dumps(get(staff(), "reports"))
    assert ann.password not in text and bob.password not in text
    assert issue_token(ann.pk) not in text and "email" not in text and "password" not in text
