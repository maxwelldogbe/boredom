"""Routes under /api/ for Nemesis and the wallet (player side)."""

from django.urls import path

from accounts.views import by_method
from nemesis import views

urlpatterns = [
    path("nemesis/status", views.status, name="nemesis-status"),
    path("nemesis/id", views.submit_id, name="nemesis-id"),
    path("nemesis/activate", views.activate, name="nemesis-activate"),
    path("nemesis/deactivate", views.deactivate, name="nemesis-deactivate"),
    path("wallet", views.wallet, name="wallet"),
    path("wallet/entries", views.entries, name="wallet-entries"),
    path("wallet/payment-details", views.payment_details, name="wallet-payment-details"),
    path(
        "wallet/deposits",
        by_method(get=views.deposits, post=views.create_deposit),
        name="wallet-deposits",
    ),
    path(
        "wallet/deposits/<int:deposit_id>/submit",
        views.submit_deposit,
        name="wallet-deposit-submit",
    ),
    path(
        "wallet/deposits/<int:deposit_id>/cancel",
        views.cancel_deposit,
        name="wallet-deposit-cancel",
    ),
    path("wallet/payout-destination", views.payout_destination, name="wallet-payout"),
    path(
        "wallet/withdrawals",
        by_method(get=views.withdrawals, post=views.create_withdrawal),
        name="wallet-withdrawals",
    ),
    path(
        "wallet/withdrawals/<int:withdrawal_id>/cancel",
        views.cancel_withdrawal,
        name="wallet-withdrawal-cancel",
    ),
    path("wallet/limits", views.limits, name="wallet-limits"),
    path("wallet/exclude", views.exclude, name="wallet-exclude"),
]
