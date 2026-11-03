"""Routes under /api/admin/ for Nemesis staff tools (two-factor, ID review, money)."""

from django.urls import path

from nemesis import admin_api as a

urlpatterns = [
    path("2fa/setup", a.twofa_setup, name="admin-2fa-setup"),
    path("2fa/confirm", a.twofa_confirm, name="admin-2fa-confirm"),
    path("2fa/step-up", a.twofa_step_up, name="admin-2fa-step-up"),
    path("ids", a.id_queue, name="admin-ids"),
    path("ids/<int:verification_id>", a.id_detail, name="admin-id"),
    path("ids/<int:verification_id>/image/<slug:side>", a.id_image, name="admin-id-image"),
    path("ids/<int:verification_id>/approve", a.id_approve, name="admin-id-approve"),
    path("ids/<int:verification_id>/reject", a.id_reject, name="admin-id-reject"),
    path("money/overview", a.overview, name="admin-money-overview"),
    path("money/deposits", a.deposit_queue, name="admin-deposits"),
    path("money/deposits/<int:deposit_id>", a.deposit_detail, name="admin-deposit"),
    path(
        "money/deposits/<int:deposit_id>/approve", a.deposit_approve, name="admin-deposit-approve"
    ),
    path("money/deposits/<int:deposit_id>/reject", a.deposit_reject, name="admin-deposit-reject"),
    path("money/withdrawals", a.withdrawal_queue, name="admin-withdrawals"),
    path("money/withdrawals/<int:withdrawal_id>", a.withdrawal_detail, name="admin-withdrawal"),
    path(
        "money/withdrawals/<int:withdrawal_id>/approve",
        a.withdrawal_approve,
        name="admin-withdrawal-approve",
    ),
    path(
        "money/withdrawals/<int:withdrawal_id>/mark-paid",
        a.withdrawal_mark_paid,
        name="admin-withdrawal-paid",
    ),
    path(
        "money/withdrawals/<int:withdrawal_id>/reject",
        a.withdrawal_reject,
        name="admin-withdrawal-reject",
    ),
    path("money/adjustments", a.adjustments, name="admin-adjustments"),
    path("money/adjustments/propose", a.adjustment_propose, name="admin-adjustment-propose"),
    path(
        "money/adjustments/<int:adjustment_id>/<slug:action>",
        a.adjustment_decide,
        name="admin-adjustment-decide",
    ),
    path("money/merchant", a.merchant_dispatch, name="admin-merchant"),
    path(
        "money/merchant/<int:merchant_id>/approve",
        a.merchant_approve,
        name="admin-merchant-approve",
    ),
    path("money/flags", a.flags_dispatch, name="admin-flags"),
    path("money/flags/approve", a.flag_approve, name="admin-flags-approve"),
    path("money/reconcile", a.reconcile_dispatch, name="admin-reconcile"),
    path("money/users/<int:user_id>", a.user_money, name="admin-user-money"),
    path(
        "money/users/<int:user_id>/remove-exclusion",
        a.remove_exclusion,
        name="admin-user-remove-exclusion",
    ),
    path("money/audit", a.money_audit, name="admin-money-audit"),
]
