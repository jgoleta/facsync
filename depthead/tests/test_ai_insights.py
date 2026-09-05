import copy
from datetime import timedelta
import json
from types import SimpleNamespace
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.utils import timezone

from depthead.models import CollegeAIInsight
from depthead.services.ai_insights import (
    generate_ai_insights,
    sanitize_analytics_for_ai,
)


@override_settings(
    GEMINI_API_KEY="test-api-key",
    GEMINI_MODEL="gemini-3.5-flash",
    GEMINI_INSIGHTS_REFRESH_DAYS=7,
)
class AIInsightsServiceTests(TestCase):
    def setUp(self):
        self.analytics = {
            "schema_version": "1.0",
            "scope": {
                "college_code": "CCS",
                "college_name": "College of Computer Studies",
                "timezone": "Asia/Manila",
            },
            "period": {
                "start_date": "2026-09-01",
                "end_date": "2026-09-05",
                "generated_at": "2026-09-05T10:00:00+08:00",
                "is_complete": False,
            },
            "consultations": {
                "total_records": 10,
                "status_distribution": {"completed": 6, "pending": 4},
            },
            "consultation_patterns": {"peak_hour": {"hours": [10], "count": 3}},
            "request_patterns": {"peak_hour": {"hours": [9], "count": 4}},
            "faculty_availability": {
                "current": {"availability_rate_percent": 50.0},
                "historical_proxy": {"rate_percent": 45.0},
            },
            "student_behavior": {"unique_students": 4, "repeat_students": 2},
            "faculty_workload": {
                "items": [
                    {
                        "faculty_key": "faculty:F-001",
                        "total_requests": 10,
                    }
                ]
            },
            "walk_ins": {"total": 3, "timing": {"timing_is_proxy": True}},
            "trends": {"growth_percent": 25.0, "growth_comparable": False},
            "capacity": {"authoritatively_calculable": False},
            "data_quality": {
                "confidence": "low",
                "consultation_sample_size": 10,
                "warnings": ["Current period is incomplete."],
            },
            "ignored_internal_section": {"secret": "do-not-send"},
        }
        self.valid_content = {
            "summary": "The available data suggests a peak at 20:00.",
            "key_insights": [
                {
                    "title": "Recorded consultations",
                    "description": "Six of the recorded requests are completed.",
                }
            ],
            "concerns": [
                {
                    "title": "Limited sample",
                    "description": "More historical data is needed.",
                    "severity": "warning",
                }
            ],
            "recommendations": [
                {
                    "title": "Continue monitoring",
                    "description": "Review the aggregates again after more records accumulate.",
                }
            ],
        }

    def _client_mock(self, client_class, response=None):
        client = client_class.return_value
        client.models.generate_content.return_value = response or SimpleNamespace(
            parsed=self.valid_content,
            text=None,
        )
        return client

    @patch("depthead.services.ai_insights.genai.Client")
    def test_successful_structured_output_is_json_safe(self, client_class):
        self._client_mock(client_class)

        result = generate_ai_insights(self.analytics)

        self.assertTrue(result["available"])
        self.assertIsNone(result["error"])
        self.assertEqual(result["concerns"][0]["severity"], "warning")
        self.assertEqual(
            result["summary"],
            "The available data suggests a peak at 8:00 PM.",
        )
        self.assertNotIn("data_limitations", result)
        self.assertEqual(result["model"], "gemini-3.5-flash")
        self.assertTrue(result["generated_at"])
        self.assertTrue(result["refresh_after"])
        self.assertFalse(result["stale"])
        record = CollegeAIInsight.objects.get(college_code="CCS")
        self.assertEqual(record.insights["summary"], result["summary"])
        self.assertGreater(record.refresh_after, record.generated_at)
        config = client_class.return_value.models.generate_content.call_args.kwargs["config"]
        self.assertEqual(
            config.response_json_schema["properties"]["concerns"]["items"]
            ["properties"]["severity"]["enum"],
            ["info", "warning", "critical"],
        )
        json.dumps(result)

    @patch("depthead.services.ai_insights.genai.Client")
    def test_api_failure_returns_safe_fallback(self, client_class):
        client = self._client_mock(client_class)
        client.models.generate_content.side_effect = RuntimeError(
            "private upstream payload and test-api-key"
        )

        result = generate_ai_insights(self.analytics)

        self.assertFalse(result["available"])
        self.assertEqual(result["error"], "AI insights are temporarily unavailable.")
        self.assertNotIn("private upstream", json.dumps(result))
        self.assertNotIn("test-api-key", json.dumps(result))

    @patch("depthead.services.ai_insights.genai.Client")
    def test_invalid_response_returns_safe_fallback(self, client_class):
        self._client_mock(
            client_class,
            SimpleNamespace(
                parsed=None,
                text='{"summary":"Incomplete","concerns":[{"severity":"urgent"}]}',
            ),
        )

        result = generate_ai_insights(self.analytics)

        self.assertFalse(result["available"])
        self.assertEqual(result["key_insights"], [])

    @override_settings(GEMINI_API_KEY="")
    @patch("depthead.services.ai_insights.genai.Client")
    def test_missing_api_key_does_not_create_client(self, client_class):
        result = generate_ai_insights(self.analytics)

        self.assertFalse(result["available"])
        client_class.assert_not_called()

    @patch("depthead.services.ai_insights.genai.Client")
    def test_prompt_includes_low_confidence_and_capacity_restrictions(self, client_class):
        client = self._client_mock(client_class)

        generate_ai_insights(self.analytics)

        prompt = client.models.generate_content.call_args.kwargs["contents"]
        self.assertIn("LOW-CONFIDENCE CONTEXT", prompt)
        self.assertIn("more historical data", prompt)
        self.assertIn("CAPACITY RESTRICTION", prompt)
        self.assertIn("Do not claim a supply-demand gap", prompt)
        self.assertIn("12-hour clock with AM or PM", prompt)
        self.assertIn("never use 24-hour or military time", prompt)

    @patch("depthead.services.ai_insights.genai.Client")
    def test_pii_and_credentials_are_removed_without_mutating_input(self, client_class):
        client = self._client_mock(client_class)
        contaminated = copy.deepcopy(self.analytics)
        contaminated["consultations"].update({
            "student_name": "Private Student",
            "email": "student@example.com",
            "student_id": "2026-0001",
            "oauth_token": "private-oauth-token",
            "message": "A private consultation message",
            "notes": "Contact hidden@example.com or +63 917 123 4567 if needed.",
        })
        original = copy.deepcopy(contaminated)

        generate_ai_insights(contaminated)

        prompt = client.models.generate_content.call_args.kwargs["contents"]
        for private_value in (
            "Private Student",
            "student@example.com",
            "2026-0001",
            "private-oauth-token",
            "A private consultation message",
            "hidden@example.com",
            "+63 917 123 4567",
            "faculty:F-001",
        ):
            self.assertNotIn(private_value, prompt)
        self.assertIn("[redacted email]", prompt)
        self.assertIn("[redacted phone]", prompt)
        self.assertEqual(contaminated, original)

    def test_sanitizer_keeps_only_interpretation_sections(self):
        sanitized = sanitize_analytics_for_ai(self.analytics)

        self.assertNotIn("schema_version", sanitized)
        self.assertNotIn("ignored_internal_section", sanitized)
        self.assertNotIn("generated_at", sanitized["period"])
        self.assertNotIn("faculty_key", sanitized["faculty_workload"]["items"][0])

    @patch("depthead.services.ai_insights.genai.Client")
    def test_database_reuses_success_for_same_analytics(self, client_class):
        client = self._client_mock(client_class)

        first = generate_ai_insights(self.analytics)
        second = generate_ai_insights(self.analytics)

        self.assertEqual(first["summary"], second["summary"])
        self.assertEqual(first["source"], "gemini")
        self.assertEqual(second["source"], "database")
        self.assertEqual(client.models.generate_content.call_count, 1)
        self.assertEqual(CollegeAIInsight.objects.count(), 1)

    @patch("depthead.services.ai_insights.genai.Client")
    def test_weekly_record_is_reused_when_analytics_change(self, client_class):
        client = self._client_mock(client_class)
        changed = copy.deepcopy(self.analytics)
        changed["consultations"]["total_records"] = 11

        generate_ai_insights(self.analytics)
        generate_ai_insights(changed)

        self.assertEqual(client.models.generate_content.call_count, 1)

    @patch("depthead.services.ai_insights.genai.Client")
    def test_expired_record_is_refreshed(self, client_class):
        client = self._client_mock(client_class)
        generate_ai_insights(self.analytics)
        CollegeAIInsight.objects.update(
            refresh_after=timezone.now() - timedelta(seconds=1)
        )

        result = generate_ai_insights(self.analytics)

        self.assertFalse(result["stale"])
        self.assertEqual(client.models.generate_content.call_count, 2)

    @patch("depthead.services.ai_insights.genai.Client")
    def test_expired_record_is_served_stale_when_refresh_fails(self, client_class):
        client = self._client_mock(client_class)
        first = generate_ai_insights(self.analytics)
        CollegeAIInsight.objects.update(
            refresh_after=timezone.now() - timedelta(seconds=1)
        )
        client.models.generate_content.side_effect = RuntimeError("provider unavailable")

        result = generate_ai_insights(self.analytics)

        self.assertTrue(result["available"])
        self.assertTrue(result["stale"])
        self.assertEqual(result["summary"], first["summary"])

    @patch("depthead.services.ai_insights.genai.Client")
    def test_force_refresh_bypasses_cache(self, client_class):
        client = self._client_mock(client_class)

        generate_ai_insights(self.analytics)
        generate_ai_insights(self.analytics, force_refresh=True)

        self.assertEqual(client.models.generate_content.call_count, 2)
