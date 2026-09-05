"""Gemini interpretation layer for the canonical College Head analytics payload."""

from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, timedelta
import hashlib
import json
import logging
import re
from typing import Annotated, Literal

from django.conf import settings
from django.utils import timezone
from google import genai
from google.genai import types
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, ValidationError

from ..models import CollegeAIInsight


logger = logging.getLogger(__name__)

GEMINI_MODEL = "gemini-3.5-flash"
DEFAULT_REFRESH_DAYS = 7

ALLOWED_ANALYTICS_SECTIONS = (
    "scope",
    "period",
    "consultations",
    "consultation_patterns",
    "request_patterns",
    "faculty_availability",
    "student_behavior",
    "faculty_workload",
    "walk_ins",
    "trends",
    "capacity",
    "data_quality",
)

SENSITIVE_KEYS = {
    "api_key",
    "access_token",
    "refresh_token",
    "oauth_token",
    "token",
    "secret",
    "password",
    "username",
    "user_name",
    "student_name",
    "faculty_name",
    "first_name",
    "last_name",
    "full_name",
    "email",
    "email_address",
    "phone",
    "phone_number",
    "student_id",
    "faculty_id",
    "student_key",
    "faculty_key",
    "message",
    "messages",
    "calendar_credentials",
    "google_calendar_credentials",
    "generated_at",
}

EMAIL_PATTERN = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
GOOGLE_KEY_PATTERN = re.compile(r"\bAIza[0-9A-Za-z_-]{20,}\b")
OAUTH_PATTERN = re.compile(r"\bya29\.[0-9A-Za-z_-]+\b")
PHONE_PATTERN = re.compile(r"(?<!\w)(?:\+?\d[\d ()-]{8,}\d)(?!\w)")
MILITARY_TIME_PATTERN = re.compile(
    r"\b([01]?\d|2[0-3]):([0-5]\d)(?:\s*hours?)?\b(?!\s*(?:AM|PM)\b)",
    re.I,
)

TitleText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=160),
]
DescriptionText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=1200),
]
class InsightItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: TitleText
    description: DescriptionText


class ConcernItem(InsightItem):
    severity: Literal["info", "warning", "critical"]


class AIInsightsContent(BaseModel):
    """Strict schema requested from Gemini and validated again locally."""

    model_config = ConfigDict(extra="forbid")

    summary: DescriptionText
    key_insights: list[InsightItem] = Field(default_factory=list, max_length=8)
    concerns: list[ConcernItem] = Field(default_factory=list, max_length=8)
    recommendations: list[InsightItem] = Field(default_factory=list, max_length=8)


GEMINI_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "key_insights": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                },
                "required": ["title", "description"],
            },
        },
        "concerns": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                    "severity": {
                        "type": "string",
                        "enum": ["info", "warning", "critical"],
                    },
                },
                "required": ["title", "description", "severity"],
            },
        },
        "recommendations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                },
                "required": ["title", "description"],
            },
        },
    },
    "required": [
        "summary",
        "key_insights",
        "concerns",
        "recommendations",
    ],
}


SYSTEM_INSTRUCTION = """
You are an analytics assistant for FacSync, a faculty availability and
consultation management system. You help a College Head understand aggregated
operational analytics. You are an interpretation layer only; Django has already
performed every authoritative calculation.

Use only the supplied analytics data. Do not calculate replacement statistics,
invent missing values, invent causes for trends, or infer student motivations
beyond recorded agenda categories. Do not infer faculty misconduct, poor
performance, or personal characteristics. Do not make disciplinary or other
high-impact decisions. Do not expose or request student or faculty identities.

Do not claim actual consultation occurrence when a metric uses scheduled-time
proxies. Do not claim a supply-demand gap, faculty shortage, or capacity
utilization when capacity.authoritatively_calculable is false. Do not present
historical availability proxies as exact historical availability. Do not
present walk-in timing proxies as exact service duration.

Respect every data-quality warning. When confidence is low, use cautious phrases
such as "The available data suggests" or "Early observations indicate", and say
that more historical data is needed before drawing a strong conclusion. Never
say that low-confidence data proves or clearly demonstrates a conclusion. If the
period is incomplete, do not describe period-over-period differences as a
definitive trend.

Separate observations from recommendations. Recommendations must be reasonable,
low-risk, and directly supported by the supplied aggregates. Return only the
requested structured response.
""".strip()


def _normalized_key(key):
    return re.sub(r"[^a-z0-9]+", "_", str(key).strip().lower()).strip("_")


def _is_sensitive_key(key):
    normalized = _normalized_key(key)
    return (
        normalized in SENSITIVE_KEYS
        or normalized.endswith("_email")
        or normalized.endswith("_phone")
        or normalized.endswith("_token")
        or normalized.endswith("_password")
        or (normalized.endswith("_id") and normalized != "college_code")
    )


def _sanitize_string(value):
    value = EMAIL_PATTERN.sub("[redacted email]", value)
    value = GOOGLE_KEY_PATTERN.sub("[redacted credential]", value)
    value = OAUTH_PATTERN.sub("[redacted credential]", value)
    return PHONE_PATTERN.sub("[redacted phone]", value)


def _twelve_hour_time(match):
    hour = int(match.group(1))
    minute = match.group(2)
    suffix = "AM" if hour < 12 else "PM"
    display_hour = hour % 12 or 12
    return f"{display_hour}:{minute} {suffix}"


def _format_output_times(value):
    if isinstance(value, dict):
        return {key: _format_output_times(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_format_output_times(item) for item in value]
    if isinstance(value, str):
        return MILITARY_TIME_PATTERN.sub(_twelve_hour_time, value)
    return value


def _sanitize_value(value):
    if isinstance(value, dict):
        return {
            str(key): _sanitize_value(item)
            for key, item in value.items()
            if not _is_sensitive_key(key)
        }
    if isinstance(value, (list, tuple)):
        return [_sanitize_value(item) for item in value]
    if isinstance(value, str):
        return _sanitize_string(value)
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return "[unsupported value removed]"


def sanitize_analytics_for_ai(analytics):
    """Return a minimized, defensive copy without identity or credential fields."""

    if not isinstance(analytics, dict):
        raise TypeError("analytics must be a dictionary")
    minimized = {
        section: analytics[section]
        for section in ALLOWED_ANALYTICS_SECTIONS
        if section in analytics
    }
    return _sanitize_value(minimized)


def _model_name():
    return getattr(settings, "GEMINI_MODEL", GEMINI_MODEL) or GEMINI_MODEL


def _refresh_interval():
    configured = getattr(settings, "GEMINI_INSIGHTS_REFRESH_DAYS", DEFAULT_REFRESH_DAYS)
    try:
        return timedelta(days=max(int(configured), 1))
    except (TypeError, ValueError):
        return timedelta(days=DEFAULT_REFRESH_DAYS)


def _serialized_payload(analytics):
    return json.dumps(
        analytics,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )


def _analytics_hash(serialized_payload):
    return hashlib.sha256(serialized_payload.encode("utf-8")).hexdigest()


def _prompt_for(analytics, serialized_payload):
    context_notes = []
    data_quality = analytics.get("data_quality") or {}
    if data_quality.get("confidence") == "low":
        context_notes.append(
            "LOW-CONFIDENCE CONTEXT: Use explicitly cautious language and state "
            "that more historical data is needed before strong conclusions."
        )
    period = analytics.get("period") or {}
    if period.get("is_complete") is False:
        context_notes.append(
            "INCOMPLETE-PERIOD CONTEXT: Do not present comparisons as definitive trends."
        )
    capacity = analytics.get("capacity") or {}
    if capacity.get("authoritatively_calculable") is False:
        context_notes.append(
            "CAPACITY RESTRICTION: Capacity is not authoritatively calculable. "
            "Do not claim a supply-demand gap, faculty shortage, or utilization rate."
        )

    notes = "\n".join(context_notes) or "No additional context flags."
    return (
        "Interpret the aggregated FacSync analytics below. All values are "
        "authoritative Django outputs; do not replace or recalculate them. "
        "Keep the summary concise and return at most four items in each list. "
        "Use only the 12-hour clock with AM or PM in your response; never use "
        "24-hour or military time (write 8:00 PM, not 20:00).\n\n"
        f"Context flags:\n{notes}\n\n"
        f"Analytics JSON:\n{serialized_payload}"
    )


def _validated_content(response):
    parsed = getattr(response, "parsed", None)
    if isinstance(parsed, AIInsightsContent):
        return parsed
    if isinstance(parsed, dict):
        return AIInsightsContent.model_validate(parsed)
    if isinstance(parsed, str):
        return AIInsightsContent.model_validate_json(parsed)

    response_text = getattr(response, "text", None)
    if not response_text:
        raise ValueError("Gemini returned an empty response.")
    return AIInsightsContent.model_validate_json(response_text)


def _unavailable_result():
    return {
        "available": False,
        "error": "AI insights are temporarily unavailable.",
        "summary": None,
        "key_insights": [],
        "concerns": [],
        "recommendations": [],
        "model": _model_name(),
        "generated_at": None,
        "refresh_after": None,
        "stale": False,
        "source": "unavailable",
    }


def _result_from_record(record, stale=False):
    stored = record.insights
    if not isinstance(stored, dict) or stored.get("available") is not True:
        raise ValueError("Stored AI insight is not a successful result.")
    content = AIInsightsContent.model_validate({
        "summary": stored.get("summary"),
        "key_insights": stored.get("key_insights", []),
        "concerns": stored.get("concerns", []),
        "recommendations": stored.get("recommendations", []),
    })
    return {
        "available": True,
        "error": None,
        **_format_output_times(content.model_dump(mode="json")),
        "model": record.model_name,
        "generated_at": record.generated_at.isoformat(),
        "refresh_after": record.refresh_after.isoformat(),
        "stale": stale,
        "source": "database",
    }


def _safe_stored_result(record, stale=False):
    if record is None:
        return None
    try:
        return _result_from_record(record, stale=stale)
    except (TypeError, ValueError, ValidationError):
        logger.warning(
            "Stored Gemini insight failed validation for college %s.",
            record.college_code,
        )
        return None


def get_stored_ai_insights(college_code, include_stale=False):
    """Return a validated persisted insight without calculating analytics."""

    normalized_code = str(college_code or "").strip().upper()
    if not normalized_code:
        return None
    record = CollegeAIInsight.objects.filter(
        college_code__iexact=normalized_code
    ).first()
    if record is None:
        return None
    is_stale = record.refresh_after <= timezone.now()
    if is_stale and not include_stale:
        return None
    result = _safe_stored_result(record, stale=is_stale)
    return deepcopy(result) if result is not None else None


def generate_ai_insights(analytics, force_refresh=False):
    """Return a weekly persisted Gemini interpretation of canonical analytics."""

    try:
        sanitized = sanitize_analytics_for_ai(analytics)
        serialized = _serialized_payload(sanitized)
        analytics_hash = _analytics_hash(serialized)
        college_code = str(
            sanitized.get("scope", {}).get("college_code") or ""
        ).strip().upper()
        if not college_code:
            raise ValueError("Analytics scope must contain a college code.")

        stored_record = CollegeAIInsight.objects.filter(
            college_code__iexact=college_code
        ).first()
        now = timezone.now()
        if (
            stored_record is not None
            and not force_refresh
            and stored_record.refresh_after > now
        ):
            stored_result = _safe_stored_result(stored_record)
            if stored_result is not None:
                return deepcopy(stored_result)

        api_key = getattr(settings, "GEMINI_API_KEY", None)
        if not api_key:
            logger.info("Gemini insights skipped because no API key is configured.")
            stale_result = _safe_stored_result(stored_record, stale=True)
            return deepcopy(stale_result) if stale_result else _unavailable_result()

        model_name = _model_name()
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=model_name,
            contents=_prompt_for(sanitized, serialized),
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_INSTRUCTION,
                response_mime_type="application/json",
                response_json_schema=GEMINI_RESPONSE_SCHEMA,
                temperature=0.2,
                max_output_tokens=2048,
                automatic_function_calling=types.AutomaticFunctionCallingConfig(
                    disable=True,
                ),
                thinking_config=types.ThinkingConfig(thinking_budget=0),
            ),
        )
        content = _validated_content(response)
        formatted_content = _format_output_times(content.model_dump(mode="json"))
        generated_at = timezone.now()
        refresh_after = generated_at + _refresh_interval()
        result = {
            "available": True,
            "error": None,
            **formatted_content,
            "model": model_name,
            "generated_at": generated_at.isoformat(),
            "refresh_after": refresh_after.isoformat(),
            "stale": False,
            "source": "gemini",
        }
        CollegeAIInsight.objects.update_or_create(
            college_code=college_code,
            defaults={
                "analytics_hash": analytics_hash,
                "insights": result,
                "model_name": model_name,
                "generated_at": generated_at,
                "refresh_after": refresh_after,
            },
        )
        return deepcopy(result)
    except Exception as exc:  # SDK, transport, parsing, and validation failures.
        stale_result = _safe_stored_result(
            locals().get("stored_record"),
            stale=True,
        )
        if stale_result is not None:
            logger.warning(
                "Gemini refresh failed; serving stored insights for college %s.",
                stored_record.college_code,
            )
            return deepcopy(stale_result)
        if isinstance(exc, ValidationError):
            issues = [
                {
                    "location": ".".join(map(str, error["loc"])) or "response",
                    "type": error["type"],
                }
                for error in exc.errors(include_input=False, include_url=False)
            ]
            logger.warning("Gemini response validation failed: %s", issues)
            return _unavailable_result()
        logger.warning(
            "Gemini insights generation failed (%s).",
            type(exc).__name__,
        )
        return _unavailable_result()
