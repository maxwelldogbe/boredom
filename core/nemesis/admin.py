"""Nemesis models in the Django admin: view only for staff (no add, change or delete).

Money and ID actions go through the audited, step-up protected staff API instead. ID images,
storage paths, ID number hashes and TOTP secrets are never shown here.
"""

from django.contrib import admin
from django.http import HttpRequest

from nemesis.models import (
    AdjustmentRequest,
    DepositRequest,
    IdVerification,
    LedgerAccount,
    LedgerEntry,
    LedgerTransaction,
    MerchantDetails,
    NemesisProfile,
    PlatformFlags,
    ReconciliationReport,
    StaffSecurity,
    WithdrawalRequest,
)


class ViewOnlyAdmin(admin.ModelAdmin):
    def has_add_permission(self, request: HttpRequest, obj=None) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj=None) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj=None) -> bool:
        return False

    def has_view_permission(self, request: HttpRequest, obj=None) -> bool:
        return request.user.is_active and request.user.is_staff

    def has_module_permission(self, request: HttpRequest) -> bool:
        return request.user.is_active and request.user.is_staff


@admin.register(NemesisProfile)
class NemesisProfileAdmin(ViewOnlyAdmin):
    list_display = ("user", "active", "activated_at", "excluded_until", "excluded_permanent")
    list_filter = ("active", "excluded_permanent")
    exclude = ("payout_number",)


@admin.register(IdVerification)
class IdVerificationAdmin(ViewOnlyAdmin):
    list_display = ("pk", "user", "id_type", "status", "attempt_number", "created_at")
    list_filter = ("status", "id_type")
    exclude = ("id_number_hash", "front_path", "back_path", "dob")


@admin.register(LedgerAccount)
class LedgerAccountAdmin(ViewOnlyAdmin):
    list_display = ("kind", "user", "balance")
    list_filter = ("kind",)


@admin.register(LedgerTransaction)
class LedgerTransactionAdmin(ViewOnlyAdmin):
    list_display = ("id", "kind", "idempotency_key", "created_at")
    list_filter = ("kind",)
    ordering = ("-created_at",)


@admin.register(LedgerEntry)
class LedgerEntryAdmin(ViewOnlyAdmin):
    list_display = ("transaction", "account", "amount", "balance_after", "created_at")
    list_select_related = ("transaction", "account")
    ordering = ("-id",)


@admin.register(DepositRequest)
class DepositRequestAdmin(ViewOnlyAdmin):
    list_display = ("reference", "user", "amount_requested", "status", "created_at")
    list_filter = ("status",)
    ordering = ("-created_at",)


@admin.register(WithdrawalRequest)
class WithdrawalRequestAdmin(ViewOnlyAdmin):
    list_display = ("pk", "user", "amount", "status", "eligible_at", "created_at")
    list_filter = ("status",)
    ordering = ("-created_at",)
    exclude = ("payout_snapshot",)


@admin.register(MerchantDetails)
class MerchantDetailsAdmin(ViewOnlyAdmin):
    list_display = ("network", "account_name", "active", "created_at")


@admin.register(PlatformFlags)
class PlatformFlagsAdmin(ViewOnlyAdmin):
    list_display = ("deposits_enabled", "withdrawals_enabled", "staking_enabled", "updated_at")


@admin.register(AdjustmentRequest)
class AdjustmentRequestAdmin(ViewOnlyAdmin):
    list_display = ("pk", "user", "amount", "status", "created_at")
    list_filter = ("status",)


@admin.register(ReconciliationReport)
class ReconciliationReportAdmin(ViewOnlyAdmin):
    list_display = ("date", "reported_balance", "ledger_liabilities", "difference", "ok")


@admin.register(StaffSecurity)
class StaffSecurityAdmin(ViewOnlyAdmin):
    list_display = ("user", "enrolled_at", "last_step_up_at")
    fields = ("user", "enrolled_at", "last_step_up_at")
