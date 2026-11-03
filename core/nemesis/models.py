"""Nemesis data: the opt-in profile, ID age checks, the double-entry ledger and money requests.

Every amount is an integer number of pesewas (BigIntegerField); never a float or Decimal.
Only nemesis.ledger changes LedgerAccount balances, and LedgerEntry rows are never updated or
deleted. Records point at the user with SET_NULL so deleting an account (allowed only with no
funds and nothing open) keeps the ledger whole and zero-sum.
"""

import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q

PHONE_MAX = 20
NAME_MAX = 100
REASON_MAX = 200
NETWORK_MAX = 32
REFERENCE_MAX = 12  # "NEM-XXXXXX"
PAYMENT_REF_MAX = 64


class PayoutMethod(models.TextChoices):
    MOBILE_MONEY = "mobile_money"
    BANK = "bank"


class NemesisProfile(models.Model):
    """A registered player's Nemesis switch, limits, self-exclusion and payout destination."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="nemesis"
    )
    active = models.BooleanField(default=False)
    activated_at = models.DateTimeField(null=True, blank=True)
    deactivated_at = models.DateTimeField(null=True, blank=True)
    age_confirmed_at = models.DateTimeField(null=True, blank=True)
    rules_version = models.PositiveSmallIntegerField(null=True, blank=True)
    # Player-set limits (null: the platform maximum applies). Never above the platform maximums.
    deposit_daily_limit = models.BigIntegerField(null=True, blank=True)
    deposit_30d_limit = models.BigIntegerField(null=True, blank=True)
    # {"depositDailyLimit": int | null, "deposit30dLimit": int | null, "effectiveAt": iso}
    pending_limit_raise = models.JSONField(null=True, blank=True)
    excluded_until = models.DateTimeField(null=True, blank=True)
    excluded_permanent = models.BooleanField(default=False)
    payout_method = models.CharField(max_length=16, choices=PayoutMethod.choices, blank=True)
    payout_network = models.CharField(max_length=NETWORK_MAX, blank=True)
    payout_number = models.CharField(max_length=PHONE_MAX, blank=True)
    payout_account_name = models.CharField(max_length=NAME_MAX, blank=True)
    payout_effective_at = models.DateTimeField(null=True, blank=True)

    def __str__(self) -> str:
        return f"Nemesis {self.user_id} {'on' if self.active else 'off'}"


class IdVerification(models.Model):
    """One ID submission. Only the HMAC of the ID number and its last 4 characters are kept.

    When the account is deleted the images go at once and the personal fields are blanked;
    the row stays (user null) so the attempt history and the approved-hash uniqueness remain.
    """

    class Status(models.TextChoices):
        PENDING = "pending"
        APPROVED = "approved"
        REJECTED = "rejected"
        REJECTED_FINAL = "rejected_final"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="id_verifications",
    )
    id_type = models.CharField(max_length=24)
    full_name = models.CharField(max_length=NAME_MAX, blank=True)
    id_number_hash = models.CharField(max_length=64)  # hex HMAC-SHA256 with SECRET_KEY
    id_number_last4 = models.CharField(max_length=4, blank=True)
    dob = models.DateField(null=True, blank=True)
    front_path = models.CharField(max_length=255, blank=True)  # relative to PRIVATE_UPLOAD_DIR
    back_path = models.CharField(max_length=255, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    attempt_number = models.PositiveSmallIntegerField()
    rejection_reason = models.CharField(max_length=REASON_MAX, blank=True)
    flagged_duplicate = models.BooleanField(default=False)  # its ID number backs another account
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    images_deleted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["id_number_hash"],
                condition=Q(status="approved"),
                name="idv_unique_approved_hash",
            ),
            models.UniqueConstraint(
                fields=["user"], condition=Q(status="pending"), name="idv_one_pending_per_user"
            ),
        ]
        indexes = [models.Index(fields=["status", "created_at"], name="idv_status_created")]

    def __str__(self) -> str:
        return f"ID {self.pk} {self.status}"


class LedgerAccount(models.Model):
    """A balance in the zero-sum ledger. `balance` is a cache of the sum of its entries.

    external goes negative as money comes in (it is what we hold for players); every other kind
    can never be negative. System accounts (external, escrow, fees) have no user.
    """

    class Kind(models.TextChoices):
        USER = "user"
        EXTERNAL = "external"
        ESCROW = "escrow"
        WITHDRAWAL_HOLD = "withdrawal_hold"
        FEES = "fees"

    kind = models.CharField(max_length=16, choices=Kind.choices)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="ledger_accounts",
    )
    balance = models.BigIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["kind", "user"], condition=Q(user__isnull=False), name="ledger_kind_user"
            ),
            models.UniqueConstraint(
                fields=["kind"],
                condition=Q(user__isnull=True, kind__in=["external", "escrow", "fees"]),
                name="ledger_one_system_account",
            ),
            models.CheckConstraint(
                condition=Q(kind="external") | Q(balance__gte=0), name="ledger_no_negative"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.kind} {self.user_id or ''}".strip()


class LedgerTransaction(models.Model):
    """One balanced posting. A repeated idempotency_key returns the original transaction."""

    class Kind(models.TextChoices):
        DEPOSIT = "deposit"
        WITHDRAWAL_HOLD = "withdrawal_hold"
        WITHDRAWAL_PAID = "withdrawal_paid"
        WITHDRAWAL_REFUND = "withdrawal_refund"
        ADJUSTMENT = "adjustment"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    kind = models.CharField(max_length=24, choices=Kind.choices)
    idempotency_key = models.CharField(max_length=100, unique=True)
    meta = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"{self.kind} {self.idempotency_key}"


class ImmutableQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise TypeError("Ledger entries are immutable.")

    def delete(self):
        raise TypeError("Ledger entries are immutable.")


class LedgerEntry(models.Model):
    """One signed line of a transaction. Written once by nemesis.ledger; never changed."""

    transaction = models.ForeignKey(
        LedgerTransaction, on_delete=models.PROTECT, related_name="entries"
    )
    account = models.ForeignKey(LedgerAccount, on_delete=models.PROTECT, related_name="entries")
    amount = models.BigIntegerField()
    balance_after = models.BigIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    objects = ImmutableQuerySet.as_manager()

    class Meta:
        constraints = [models.CheckConstraint(condition=~Q(amount=0), name="entry_nonzero")]
        indexes = [models.Index(fields=["account", "-id"], name="entry_account_newest")]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise TypeError("Ledger entries are immutable.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise TypeError("Ledger entries are immutable.")

    def __str__(self) -> str:
        return f"{self.account} {self.amount:+d}"


class DepositRequest(models.Model):
    """A manual deposit: the player pays outside the app with `reference` in the note."""

    class Status(models.TextChoices):
        AWAITING_PAYMENT = "awaiting_payment"
        PENDING_REVIEW = "pending_review"
        APPROVED = "approved"
        REJECTED = "rejected"
        EXPIRED = "expired"
        CANCELLED = "cancelled"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="deposit_requests",
    )
    reference = models.CharField(max_length=REFERENCE_MAX, unique=True)
    amount_requested = models.BigIntegerField()
    merchant_snapshot = models.JSONField(default=dict)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.AWAITING_PAYMENT
    )
    payment_ref = models.CharField(max_length=PAYMENT_REF_MAX, null=True, blank=True)
    sender_number = models.CharField(max_length=PHONE_MAX, blank=True)
    amount_received = models.BigIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()  # end of the awaiting_payment stage
    submitted_at = models.DateTimeField(null=True, blank=True)
    # Dual approval: the first approver and the amount they confirmed.
    first_approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    first_approved_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reject_reason = models.CharField(max_length=REASON_MAX, blank=True)
    note = models.CharField(max_length=REASON_MAX, blank=True)
    ledger_tx = models.ForeignKey(
        LedgerTransaction, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["payment_ref"],
                condition=Q(status__in=["pending_review", "approved"]),
                name="deposit_unique_payment_ref",
            ),
            models.UniqueConstraint(
                fields=["user"],
                condition=Q(status__in=["awaiting_payment", "pending_review"]),
                name="deposit_one_open_per_user",
            ),
        ]
        indexes = [models.Index(fields=["status", "created_at"], name="deposit_status_created")]

    def __str__(self) -> str:
        return f"{self.reference} {self.status}"


class WithdrawalRequest(models.Model):
    """A manual payout. The amount sits in the user's withdrawal_hold until paid or refunded."""

    class Status(models.TextChoices):
        PENDING_REVIEW = "pending_review"
        APPROVED = "approved"
        PAID = "paid"
        REJECTED = "rejected"
        CANCELLED = "cancelled"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="withdrawal_requests",
    )
    amount = models.BigIntegerField()
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING_REVIEW)
    payout_snapshot = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    eligible_at = models.DateTimeField()
    first_approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    first_approved_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reject_reason = models.CharField(max_length=REASON_MAX, blank=True)
    payout_reference = models.CharField(max_length=PAYMENT_REF_MAX, blank=True)
    paid_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    paid_at = models.DateTimeField(null=True, blank=True)
    ledger_tx = models.ForeignKey(
        LedgerTransaction, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    settle_tx = models.ForeignKey(
        LedgerTransaction, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user"],
                condition=Q(status="pending_review"),
                name="withdrawal_one_pending_per_user",
            ),
        ]
        indexes = [models.Index(fields=["status", "created_at"], name="withdrawal_status_created")]

    def __str__(self) -> str:
        return f"Withdrawal {self.pk} {self.status}"


class MerchantDetails(models.Model):
    """Where players send deposits. Versioned: a change is a new row; at most one is active."""

    method = models.CharField(max_length=16, choices=PayoutMethod.choices)
    network = models.CharField(max_length=NETWORK_MAX)
    number = models.CharField(max_length=40)
    account_name = models.CharField(max_length=NAME_MAX)
    active = models.BooleanField(default=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    activated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name_plural = "merchant details"
        constraints = [
            models.UniqueConstraint(
                fields=["active"], condition=Q(active=True), name="merchant_one_active"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.network} {'active' if self.active else 'inactive'}"


class PlatformFlags(models.Model):
    """The single row of money switches. NEMESIS_ENABLED (environment) stays separate.

    Also holds the staff permissions for the money tools (assigned through groups).
    """

    deposits_enabled = models.BooleanField(default=True)
    withdrawals_enabled = models.BooleanField(default=True)
    staking_enabled = models.BooleanField(default=False)  # used in Part 2
    # Dual approval: {"field": str, "value": bool, "proposedBy": int, "proposedAt": iso}
    pending_change = models.JSONField(null=True, blank=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "platform flags"
        permissions = [
            ("review_ids", "Can review ID verifications"),
            ("review_deposits", "Can review deposits"),
            ("review_withdrawals", "Can review withdrawals"),
            ("adjust_balances", "Can propose and approve balance adjustments"),
            ("edit_merchant", "Can change merchant details"),
            ("edit_flags", "Can change platform money flags"),
        ]

    def __str__(self) -> str:
        return "Platform flags"


class AdjustmentRequest(models.Model):
    """A correction: posts new entries between a user account and external; never edits any."""

    class Status(models.TextChoices):
        PENDING = "pending"
        APPLIED = "applied"
        REJECTED = "rejected"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="adjustments",
    )
    amount = models.BigIntegerField()  # signed: positive credits the user
    reason = models.CharField(max_length=REASON_MAX)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    proposed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    decided_at = models.DateTimeField(null=True, blank=True)
    ledger_tx = models.ForeignKey(
        LedgerTransaction, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )

    class Meta:
        constraints = [models.CheckConstraint(condition=~Q(amount=0), name="adjustment_nonzero")]

    def __str__(self) -> str:
        return f"Adjustment {self.pk} {self.status}"


class ReconciliationReport(models.Model):
    """Staff-entered real balance of the receiving accounts against the ledger liabilities."""

    date = models.DateField()
    reported_balance = models.BigIntegerField()
    ledger_liabilities = models.BigIntegerField()
    difference = models.BigIntegerField()  # reported - liabilities
    ok = models.BooleanField()
    entered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"Reconciliation {self.date} {'ok' if self.ok else 'SHORT'}"


class StaffSecurity(models.Model):
    """A staff member's TOTP enrolment (RFC 6238), backup codes and last step-up."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="staff_security"
    )
    totp_secret = models.CharField(max_length=64)  # base32; set on setup, enrolled on confirm
    enrolled_at = models.DateTimeField(null=True, blank=True)
    backup_codes_hash = models.JSONField(default=list, blank=True)
    last_totp_step = models.BigIntegerField(null=True, blank=True)  # rejects replay in a step
    last_step_up_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name_plural = "staff security"

    def __str__(self) -> str:
        return f"Staff security {self.user_id}"
