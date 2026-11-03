"""Nemesis ID age verification, private image storage, retention and the opt-in."""

from datetime import date, timedelta
from pathlib import Path

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.utils import timezone

from accounts import services as account_services
from games.constants import ID_IMAGE_RETENTION_DAYS, ID_MAX_ATTEMPTS, NEMESIS_RULES_VERSION
from nemesis import ids, ledger, views
from nemesis.errors import NemesisError
from nemesis.models import IdVerification, LedgerAccount, NemesisProfile
from tests.nemesis_helpers import JPEG, PNG, account_user, auth, make_eligible

pytestmark = pytest.mark.django_db
Status = IdVerification.Status
ADULT_DOB = "1990-05-04"


@pytest.fixture(autouse=True)
def nemesis_on(settings, tmp_path: Path) -> Path:
    settings.NEMESIS_ENABLED = True
    settings.PRIVATE_UPLOAD_DIR = tmp_path
    views.id_upload_limiter.reset()
    return tmp_path


def upload(client: Client, user, *, front: bytes = PNG, name="id.png", **fields):
    data = {
        "idType": "ghana_card",
        "fullName": "Ama Mensah",
        "idNumber": "GHA-123456789-0",
        "dob": ADULT_DOB,
        "front": SimpleUploadedFile(name, front, content_type="image/png"),
        **fields,
    }
    return client.post("/api/nemesis/id", data, **auth(user))


def status(client: Client, user) -> dict:
    return client.get("/api/nemesis/status", **auth(user)).json()


def test_submission_stores_privately_and_keeps_only_hash_and_last4(client, nemesis_on) -> None:
    user = account_user()
    res = upload(client, user, back=SimpleUploadedFile("b.jpg", JPEG))
    assert res.status_code == 201
    assert res.json()["idState"] == "pending"
    assert res["Cache-Control"] == "no-store"
    v = IdVerification.objects.get(user=user)
    assert v.id_number_last4 == "7890"
    assert v.id_number_hash == ids.hash_id_number("GHA1234567890")
    assert "GHA1234567890" not in str(IdVerification.objects.filter(pk=v.pk).values().first())
    front = nemesis_on / v.front_path
    assert front.read_bytes() == PNG and v.front_path.endswith(".png")
    assert (nemesis_on / v.back_path).suffix == ".jpg"


def test_type_is_checked_by_magic_bytes_not_extension(client) -> None:
    user = account_user()
    res = upload(client, user, front=b"GIF89a" + b"\x00" * 30, name="photo.png")
    assert res.status_code == 400 and "front" in res.json()["error"]["fields"]
    assert not IdVerification.objects.exists()


def test_size_limit(client, monkeypatch) -> None:
    monkeypatch.setattr(ids, "ID_MAX_BYTES", 32)
    res = upload(client, account_user())
    assert res.json()["error"]["fields"]["front"] == "The photo is too large."


def test_attempt_limit_then_final(client) -> None:
    user, staff = account_user(), account_user(staff=True)
    for attempt in range(1, ID_MAX_ATTEMPTS + 1):
        views.id_upload_limiter.reset()
        assert upload(client, user).status_code == 201
        assert upload(client, user).json()["error"]["code"] == "INVALID_STATE"  # one pending
        v = ids.latest(user)
        ids.reject(v.pk, staff, "Blurry photo")
        body = status(client, user)
        assert body["attemptsLeft"] == ID_MAX_ATTEMPTS - attempt
    assert body["idState"] == "rejected_final"
    assert upload(client, user).json()["error"]["code"] == "INVALID_STATE"


def test_under_age_is_final_at_once_without_images(client, nemesis_on) -> None:
    user = account_user()
    dob = (timezone.localdate() - timedelta(days=365 * 17)).isoformat()
    body = upload(client, user, dob=dob).json()
    assert body["idState"] == "rejected_final"
    v = IdVerification.objects.get(user=user)
    assert v.front_path == "" and v.full_name == ""
    assert not list(nemesis_on.rglob("*.png"))


def test_staff_age_recheck_and_duplicate_id(client) -> None:
    staff = account_user(staff=True)
    first, second = account_user(), account_user()
    upload(client, first)
    upload(client, second)  # same ID number
    ids.approve(ids.latest(first).pk, staff, date(1990, 5, 4))
    with pytest.raises(NemesisError) as exc:
        ids.approve(ids.latest(second).pk, staff, date(1990, 5, 4))
    assert exc.value.code == "ID_ALREADY_USED"
    v = ids.latest(second)
    assert v.flagged_duplicate and v.status == Status.PENDING
    with pytest.raises(NemesisError) as own:
        ids.approve(v.pk, second, date(1990, 5, 4))
    assert own.value.code == "FORBIDDEN"
    third = account_user()
    upload(client, third, idNumber="X99887766")
    young = timezone.localdate() - timedelta(days=365 * 16)
    assert ids.approve(ids.latest(third).pk, staff, young).status == Status.REJECTED_FINAL


def test_retention_deletes_images(client, nemesis_on) -> None:
    user, staff = account_user(), account_user(staff=True)
    upload(client, user)
    v = ids.approve(ids.latest(user).pk, staff, date(1990, 5, 4))
    path = nemesis_on / v.front_path
    assert ids.prune_images() == 0 and path.exists()
    later = timezone.now() + timedelta(days=ID_IMAGE_RETENTION_DAYS, minutes=1)
    assert ids.prune_images(later) == 1
    v.refresh_from_db()
    assert not path.exists() and v.images_deleted_at and v.front_path == ""


def test_account_deletion_removes_images_keeps_record(client, nemesis_on) -> None:
    user = account_user()
    upload(client, user)
    v = ids.latest(user)
    path = nemesis_on / v.front_path
    account_services.delete_account(user)
    v.refresh_from_db()
    assert not path.exists()
    assert v.user_id is None and v.full_name == "" and v.dob is None and v.images_deleted_at


# ----- opt-in ----------------------------------------------------------------------------

AGREE = {"confirmAge": True, "acceptRules": True, "rulesVersion": NEMESIS_RULES_VERSION}


def activate(client: Client, user, body=None):
    return client.post(
        "/api/nemesis/activate", body or AGREE, content_type="application/json", **auth(user)
    )


def test_eligibility_numbers_and_id_required(client) -> None:
    user = account_user()
    info = status(client, user)["eligibility"]
    assert info["accountAgeOk"] is False and info["hoursLeft"] > 0
    assert info["gamesPlayed"] == 0 and info["gamesNeeded"] > 0
    assert activate(client, user).json()["error"]["code"] == "ID_REQUIRED"


def test_not_eligible_returns_the_numbers(client) -> None:
    user = account_user()
    make_eligible(user)
    user.stats.all().delete()
    err = activate(client, user).json()["error"]
    assert err["code"] == "NOT_ELIGIBLE" and err["eligibility"]["gamesNeeded"] > 0


def test_confirmations_and_rules_version_required(client) -> None:
    user = account_user(eligible=True)
    res = activate(client, user, {"confirmAge": True, "acceptRules": False, "rulesVersion": 0})
    assert set(res.json()["error"]["fields"]) == {"acceptRules", "rulesVersion"}


def test_activate_gives_no_credit_and_deactivate(client) -> None:
    user = account_user(eligible=True)
    body = activate(client, user).json()
    assert body["active"] is True
    assert activate(client, user).json()["error"]["code"] == "ALREADY_ACTIVE"
    assert not LedgerAccount.objects.filter(user=user).exists()
    assert ledger.balance(LedgerAccount.Kind.USER, user) == 0
    off = client.post(
        "/api/nemesis/deactivate", content_type="application/json", **auth(user)
    ).json()
    assert off["active"] is False


def test_exclusion_blocks_activation(client) -> None:
    user = account_user(eligible=True)
    NemesisProfile.objects.create(user=user, excluded_until=timezone.now() + timedelta(days=7))
    assert activate(client, user).json()["error"]["code"] == "EXCLUDED"


def test_disabled_routes_are_404(client, settings) -> None:
    settings.NEMESIS_ENABLED = False
    user = account_user(eligible=True)
    assert upload(client, user).status_code == 404
    assert activate(client, user).status_code == 404
