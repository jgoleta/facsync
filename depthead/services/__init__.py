"""Reusable services for College Head features."""

from .ai_insights import generate_ai_insights, get_stored_ai_insights
from .analytics import get_college_analytics

__all__ = [
    "generate_ai_insights",
    "get_college_analytics",
    "get_stored_ai_insights",
]
