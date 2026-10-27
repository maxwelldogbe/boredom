"""Give every existing account a public tag.

Safe on the live database and idempotent: tags that already exist are recorded in TakenTag,
only profiles without a tag get one, collisions are retried, and a profile that gained a tag
meanwhile (a concurrent registration) is left alone. Reversing it keeps the tags.
"""

import secrets

from django.db import IntegrityError, migrations, transaction

from games.constants import TAG_ALPHABET, TAG_LENGTH

MAX_ATTEMPTS = 50


def backfill(apps, schema_editor) -> None:
    Profile = apps.get_model("accounts", "Profile")
    TakenTag = apps.get_model("accounts", "TakenTag")
    for tag in Profile.objects.exclude(tag__isnull=True).values_list("tag", flat=True):
        TakenTag.objects.get_or_create(tag=tag)
    pending = Profile.objects.filter(tag__isnull=True).select_related("user").order_by("pk")
    for profile in pending.iterator():
        username = profile.user.username.upper()
        for _ in range(MAX_ATTEMPTS):
            tag = "".join(secrets.choice(TAG_ALPHABET) for _ in range(TAG_LENGTH))
            if username and username in tag:
                continue
            try:
                with transaction.atomic():
                    TakenTag.objects.create(tag=tag)
            except IntegrityError:
                continue
            Profile.objects.filter(pk=profile.pk, tag__isnull=True).update(tag=tag)
            break
        else:
            raise RuntimeError(f"Could not issue a unique tag for profile {profile.pk}.")


class Migration(migrations.Migration):
    dependencies = [("accounts", "0002_profile_tag")]

    operations = [migrations.RunPython(backfill, migrations.RunPython.noop)]
