"""SocialError lives apart from the services so the hub can import it before Django is ready."""


class SocialError(Exception):
    """A rejected social action. `code` is an API error code such as ALREADY_FRIENDS."""

    def __init__(self, code: str, message: str, fields: dict[str, str] | None = None) -> None:
        super().__init__(message)
        self.code, self.message, self.fields = code, message, fields
