"""Errors shown to the user as a Hebrew message."""


class FlowError(Exception):
    """A request that does not fit the task's current state, or invalid input."""

    def __init__(self, message_he: str):
        super().__init__(message_he)
        self.message_he = message_he
