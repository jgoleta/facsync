"""Shared limits for consultation-related input."""

CONSULTATION_NOTE_MAX_LENGTH = 200
CONSULTATION_NOTE_LIMIT_ERROR = (
    f"Note must be {CONSULTATION_NOTE_MAX_LENGTH} characters or fewer."
)
