"""ID age verification: validation, private image storage, staff decisions and retention.

Images are JPEG or PNG (checked by magic bytes), saved under random names in
PRIVATE_UPLOAD_DIR (never served by any public path). Only the HMAC-SHA256 of the ID number
(keyed with SECRET_KEY) and its last 4 characters are stored. File contents and ID numbers are
never logged.
"""

import hashlib
import hmac
import logging
import re
import secrets
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from django.conf import settings
from django.contrib.auth.models import User
from django.core.files.uploadedfile import UploadedFile
from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.dateparse import parse_date

from analytics.recorder import recorder
from games.constants import (
    ID_IMAGE_RETENTION_DAYS,
    ID_MAX_ATTEMPTS,
    ID_MAX_BYTES,
    ID_TYPES,
    NEMESIS_MIN_AGE_YEARS,
)
from nemesis.errors import NemesisError
from nemesis.models import IdVerification

logger = logging.getLogger(__name__)

Status = IdVerification.Status
NAME_RE = re.compile(r"^[^\W\d_]+(?:[ '.-][^\W\d_]+)*\.?$")
NAME_MIN, NAME_MAX = 2, 100
ID_NUMBER_RE = re.compile(r"^[A-Z0-9]{4,30}$")
REASON_MAX = 200
OLDEST_YEARS = 120
UNDER_AGE_MESSAGE = "We could not verify this ID."
IMAGE_DIR = "ids"
MAGIC = {b"\xff\xd8\xff": ".jpg", b"\x89PNG\r\n\x1a\n": ".png"}


# ----- validation ------------------------------------------------------------------------


def normalize_id_number(raw: str) -> str:
    """Uppercase with spaces and punctuation removed (GHA-123 456 -> GHA123456)."""
    return re.sub(r"[^A-Z0-9]", "", raw.upper())


def hash_id_number(number: str) -> str:
    return hmac.new(settings.SECRET_KEY.encode(), number.encode(), hashlib.sha256).hexdigest()


def age_on(dob: date, today: date) -> int:
    return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))


def image_extension(head: bytes) -> str | None:
    """'.jpg' or '.png' from the file's first bytes, else None (extension and type ignored)."""
    for magic, ext in MAGIC.items():
        if head.startswith(magic):
            return ext
    return None


def read_image(upload: UploadedFile | None, field: str, errors: dict[str, str]) -> bytes | None:
    if upload is None:
        return None
    if upload.size is not None and upload.size > ID_MAX_BYTES:
        errors[field] = "The photo is too large."
        return None
    data = upload.read(ID_MAX_BYTES + 1)
    if len(data) > ID_MAX_BYTES:
        errors[field] = "The photo is too large."
        return None
    if image_extension(data[:8]) is None:
        errors[field] = "Use a JPEG or PNG photo."
        return None
    return data


def _text(raw: Any) -> str:
    return raw.strip() if isinstance(raw, str) else ""


# ----- private storage -------------------------------------------------------------------


def _root() -> Path:
    return Path(settings.PRIVATE_UPLOAD_DIR)


def save_image(data: bytes) -> str:
    """Write the image under a random name; returns its path relative to PRIVATE_UPLOAD_DIR."""
    folder = _root() / IMAGE_DIR
    folder.mkdir(mode=0o700, parents=True, exist_ok=True)
    rel = f"{IMAGE_DIR}/{secrets.token_hex(16)}{image_extension(data[:8])}"
    path = _root() / rel
    with open(path, "xb") as f:
        f.write(data)
    path.chmod(0o600)
    return rel


def image_path(rel: str) -> Path | None:
    """The absolute file for a stored relative path, or None if missing or outside the root."""
    if not rel:
        return None
    root = _root().resolve()
    path = (root / rel).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        return None
    return path


def delete_images(v: IdVerification) -> None:
    for rel in (v.front_path, v.back_path):
        path = image_path(rel)
        if path is not None:
            path.unlink(missing_ok=True)


# ----- player side -----------------------------------------------------------------------


def latest(user: User) -> IdVerification | None:
    return IdVerification.objects.filter(user=user).order_by("-created_at", "-pk").first()


def id_state(user: User) -> dict[str, Any]:
    """{idState, attemptsLeft, rejectionReason} for the status endpoint."""
    rows = list(IdVerification.objects.filter(user=user).order_by("-created_at", "-pk"))
    attempts_left = max(0, ID_MAX_ATTEMPTS - len(rows))
    if any(r.status == Status.APPROVED for r in rows):
        state, reason = "approved", None
    elif not rows:
        state, reason = "none", None
    else:
        state, reason = rows[0].status, rows[0].rejection_reason or None
        if state == Status.REJECTED and attempts_left == 0:
            state = Status.REJECTED_FINAL
    return {"idState": state, "attemptsLeft": attempts_left, "rejectionReason": reason}


def submit(user: User, data: dict[str, Any], files: dict[str, UploadedFile]) -> IdVerification:
    """Validate and store one ID submission (a NemesisError explains any refusal)."""
    state = id_state(user)
    if state["idState"] in ("pending", "approved", "rejected_final"):
        raise NemesisError("INVALID_STATE", "You cannot submit an ID right now.")
    if state["attemptsLeft"] == 0:
        raise NemesisError("INVALID_STATE", "No ID attempts left.")

    errors: dict[str, str] = {}
    id_type = _text(data.get("idType"))
    if id_type not in ID_TYPES:
        errors["idType"] = "Choose an ID type."
    full_name = " ".join(_text(data.get("fullName")).split())
    if not (NAME_MIN <= len(full_name) <= NAME_MAX) or not NAME_RE.match(full_name):
        errors["fullName"] = "Enter your name as it appears on the ID."
    number = normalize_id_number(_text(data.get("idNumber")))
    if not ID_NUMBER_RE.match(number):
        errors["idNumber"] = "Enter the ID number."
    today = timezone.localdate()
    try:
        dob = parse_date(_text(data.get("dob")))
    except ValueError:
        dob = None
    if dob is None or dob >= today or age_on(dob, today) > OLDEST_YEARS:
        errors["dob"] = "Enter a valid date of birth."
    front = read_image(files.get("front"), "front", errors)
    if front is None and "front" not in errors:
        errors["front"] = "Add a photo of the front of your ID."
    back = read_image(files.get("back"), "back", errors)
    if errors:
        raise NemesisError("INVALID_INPUT", "Some fields need fixing.", errors)
    assert dob is not None and front is not None

    attempt = IdVerification.objects.filter(user=user).count() + 1
    now = timezone.now()
    if age_on(dob, today) < NEMESIS_MIN_AGE_YEARS:
        # Final at once; no images or name are kept for an under-age submission.
        v = IdVerification.objects.create(
            user=user,
            id_type=id_type,
            id_number_hash=hash_id_number(number),
            status=Status.REJECTED_FINAL,
            attempt_number=attempt,
            rejection_reason=UNDER_AGE_MESSAGE,
            reviewed_at=now,
            images_deleted_at=now,
        )
        recorder.record_event("id_rejected", user_id=user.pk)
        return v

    front_path = save_image(front)
    back_path = save_image(back) if back is not None else ""
    try:
        v = IdVerification.objects.create(
            user=user,
            id_type=id_type,
            full_name=full_name,
            id_number_hash=hash_id_number(number),
            id_number_last4=number[-4:],
            dob=dob,
            front_path=front_path,
            back_path=back_path,
            attempt_number=attempt,
        )
    except IntegrityError:  # a concurrent pending submission
        for rel in (front_path, back_path):
            path = image_path(rel)
            if path is not None:
                path.unlink(missing_ok=True)
        raise NemesisError("INVALID_STATE", "You already have an ID waiting for review.") from None
    logger.info("ID submitted: user=%s verification=%s", user.pk, v.pk)
    recorder.record_event("id_submitted", user_id=user.pk)
    return v


# ----- staff decisions (the HTTP layer adds permission and step-up checks) ---------------


def _locked_pending(verification_id: int, staff: User) -> IdVerification:
    v = IdVerification.objects.select_for_update().filter(pk=verification_id).first()
    if v is None:
        raise NemesisError("REQUEST_NOT_FOUND", "No such verification.")
    if v.user_id is not None and v.user_id == staff.pk:
        raise NemesisError("FORBIDDEN", "You cannot review your own ID.")
    if v.status != Status.PENDING:
        raise NemesisError("INVALID_STATE", "This verification was already decided.")
    return v


def approve(verification_id: int, staff: User, dob: date) -> IdVerification:
    """Approve with the date of birth the reviewer read off the image.

    Under NEMESIS_MIN_AGE_YEARS: rejected_final. ID number already approved for another
    account: ID_ALREADY_USED, and the submission is flagged (it stays pending).
    """
    today = timezone.localdate()
    if dob >= today or age_on(dob, today) > OLDEST_YEARS:
        raise NemesisError("INVALID_INPUT", "Enter a valid date of birth.", {"dob": "Invalid."})
    with transaction.atomic():
        v = _locked_pending(verification_id, staff)
        now = timezone.now()
        v.dob, v.reviewed_by, v.reviewed_at = dob, staff, now
        if age_on(dob, today) < NEMESIS_MIN_AGE_YEARS:
            v.status, v.rejection_reason = Status.REJECTED_FINAL, UNDER_AGE_MESSAGE
            v.save()
            recorder.record_event("id_rejected", user_id=v.user_id)
            return v
        duplicate = IdVerification.objects.filter(
            id_number_hash=v.id_number_hash, status=Status.APPROVED
        ).exists()
        if not duplicate:
            v.status = Status.APPROVED
            try:
                with transaction.atomic():
                    v.save()
            except IntegrityError:  # approved concurrently for another account
                duplicate = True
    if duplicate:
        IdVerification.objects.filter(pk=v.pk).update(flagged_duplicate=True)
        raise NemesisError("ID_ALREADY_USED", "This ID is already used by another account.")
    recorder.record_event("id_approved", user_id=v.user_id)
    return v


def reject(verification_id: int, staff: User, reason: str) -> IdVerification:
    """Reject with a reason; the last allowed attempt becomes rejected_final."""
    reason = " ".join(reason.split()) if isinstance(reason, str) else ""
    if not reason or len(reason) > REASON_MAX:
        raise NemesisError("INVALID_INPUT", "Give a reason.", {"reason": "Required."})
    with transaction.atomic():
        v = _locked_pending(verification_id, staff)
        final = v.attempt_number >= ID_MAX_ATTEMPTS
        v.status = Status.REJECTED_FINAL if final else Status.REJECTED
        v.rejection_reason, v.reviewed_by, v.reviewed_at = reason, staff, timezone.now()
        v.save()
    recorder.record_event("id_rejected", user_id=v.user_id)
    return v


# ----- retention and account deletion ----------------------------------------------------


def prune_images(now: datetime | None = None) -> int:
    """Delete images ID_IMAGE_RETENTION_DAYS after the decision (0 keeps them)."""
    if ID_IMAGE_RETENTION_DAYS <= 0:
        return 0
    cutoff = (now or timezone.now()) - timedelta(days=ID_IMAGE_RETENTION_DAYS)
    due = IdVerification.objects.filter(
        images_deleted_at__isnull=True, reviewed_at__lte=cutoff
    ).exclude(status=Status.PENDING)
    count = 0
    for v in due:
        delete_images(v)
        IdVerification.objects.filter(pk=v.pk).update(
            front_path="", back_path="", images_deleted_at=now or timezone.now()
        )
        count += 1
    return count


def forget_user(user: User) -> None:
    """Account deletion: remove the images now and blank the personal fields (rows stay)."""
    now = timezone.now()
    for v in IdVerification.objects.filter(user=user):
        delete_images(v)
    IdVerification.objects.filter(user=user, images_deleted_at__isnull=True).update(
        images_deleted_at=now
    )
    IdVerification.objects.filter(user=user).update(
        full_name="", id_number_last4="", dob=None, front_path="", back_path=""
    )
