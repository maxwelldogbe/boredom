"""Accounts in the admin: disable, enable and delete (the shared, anonymising deletion).

Every action is written to Django's admin LogEntry.
"""

from django.contrib import admin, messages
from django.contrib.admin.options import ActionLocation
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import User
from django.db.models import QuerySet
from django.http import HttpRequest
from django.template.response import TemplateResponse

from accounts import services
from accounts.models import RecoveryRequest
from social import notify


def set_active(request: HttpRequest, model_admin: admin.ModelAdmin, users: QuerySet, active: bool):
    for user in users:
        if user.is_active != active:
            user.is_active = active
            user.save(update_fields=["is_active"])
            if not active:
                notify.account_gone(user.pk)
            model_admin.log_change(
                request, user, "Enabled account" if active else "Disabled account"
            )


def delete_accounts(request: HttpRequest, model_admin: admin.ModelAdmin, users: QuerySet) -> int:
    """Log, then delete each account through services.delete_account.

    Accounts with Nemesis funds or open requests are skipped (not counted).
    """
    users = [user for user in users if not services.deletion_blocked(user)]
    model_admin.log_deletions(request, users)
    for user in users:
        services.delete_account(user)
    return len(users)


class AccountAdmin(UserAdmin):
    list_display = ("username", "nickname", "is_active", "is_staff", "date_joined", "last_login")
    list_select_related = ("profile",)
    actions = ["disable_accounts", "enable_accounts", "delete_selected_accounts"]

    @admin.display(description="Nickname", ordering="profile__nickname")
    def nickname(self, user: User) -> str:
        profile = getattr(user, "profile", None)
        return profile.nickname if profile else "—"

    def get_actions(self, request: HttpRequest, action_location=ActionLocation.CHANGE_LIST):
        actions = super().get_actions(request, action_location)
        actions.pop("delete_selected", None)  # replaced: deletion must anonymise first
        return actions

    @admin.action(description="Disable selected accounts", permissions=["change"])
    def disable_accounts(self, request: HttpRequest, queryset: QuerySet) -> None:
        set_active(request, self, queryset, False)
        self.message_user(request, "Accounts disabled.", messages.SUCCESS)

    @admin.action(description="Enable selected accounts", permissions=["change"])
    def enable_accounts(self, request: HttpRequest, queryset: QuerySet) -> None:
        set_active(request, self, queryset, True)
        self.message_user(request, "Accounts enabled.", messages.SUCCESS)

    @admin.action(
        description="Delete selected accounts (keeps games anonymised)", permissions=["delete"]
    )
    def delete_selected_accounts(self, request: HttpRequest, queryset: QuerySet):
        if request.POST.get("confirmed") == "yes":
            count = delete_accounts(request, self, queryset)
            self.message_user(request, f"Deleted {count} account(s).", messages.SUCCESS)
            if count < len(queryset):
                self.message_user(
                    request, "Accounts with Nemesis funds were not deleted.", messages.WARNING
                )
            return None
        context = {
            **self.admin_site.each_context(request),
            "title": "Delete accounts",
            "accounts": queryset,
            "action": "delete_selected_accounts",
            "action_checkbox_name": admin.helpers.ACTION_CHECKBOX_NAME,
        }
        return TemplateResponse(request, "admin/accounts/delete_accounts.html", context)

    def delete_model(self, request: HttpRequest, obj: User) -> None:
        self.delete_queryset(request, [obj])

    def delete_queryset(self, request: HttpRequest, queryset: QuerySet) -> None:
        for user in queryset:
            if services.deletion_blocked(user):
                self.message_user(
                    request, f"{user} has Nemesis funds and was not deleted.", messages.ERROR
                )
            else:
                services.delete_account(user)


admin.site.unregister(User)
admin.site.register(User, AccountAdmin)


@admin.register(RecoveryRequest)
class RecoveryRequestAdmin(admin.ModelAdmin):
    """Read-only list; staff decide from the dashboard (/admin/recovery). Registering the model
    gives approve and reject their LogEntry audit rows."""

    list_display = ("id", "created_at", "username", "status", "reviewed_by")
    list_filter = ("status",)
    readonly_fields = [
        f.name for f in RecoveryRequest._meta.fields if f.name not in ("code_digest",)
    ]
    exclude = ("code_digest",)

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False
