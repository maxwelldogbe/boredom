"""Brag coins in the Django admin: read-only (no one edits play money by hand)."""

from django.contrib import admin
from django.http import HttpRequest

from brag.models import BragEntry, BragWallet


class ReadOnly(admin.ModelAdmin):
    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj=None) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj=None) -> bool:
        return False


@admin.register(BragWallet)
class BragWalletAdmin(ReadOnly):
    list_display = ("user", "balance", "created_at")


@admin.register(BragEntry)
class BragEntryAdmin(ReadOnly):
    list_display = ("user", "kind", "amount", "balance_after", "game_id", "ref", "created_at")
    list_filter = ("kind",)
