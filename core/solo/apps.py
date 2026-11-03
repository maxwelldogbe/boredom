from django.apps import AppConfig


class SoloConfig(AppConfig):
    """Single-player games against a bot: one private room per account, records per variant."""

    name = "solo"
