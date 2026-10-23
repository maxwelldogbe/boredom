"""The `accounts_smoke` command passes and leaves no account behind."""

from io import StringIO

import pytest
from django.contrib.auth.models import User
from django.core.management import call_command

pytestmark = pytest.mark.django_db(transaction=True)


def test_accounts_smoke_command_passes_and_cleans_up() -> None:
    out = StringIO()
    call_command("accounts_smoke", stdout=out)
    assert "FAIL" not in out.getvalue()
    assert "All account checks passed." in out.getvalue()
    assert not User.objects.filter(username__startswith="smoke_").exists()
