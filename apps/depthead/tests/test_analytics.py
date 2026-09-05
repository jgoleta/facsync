import json
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.core.models import College
from apps.faculty.models import ConsultationRequest, FacultyProfile, StatusHistory, WalkInQueue
from apps.depthead.services.analytics import (
    get_college_analytics,
    get_current_availability,
    get_historical_availability_proxy,
    get_request_submission_patterns,
    normalize_period,
)


class CollegeAnalyticsTests(TestCase):
    def setUp(self):
        College.objects.get_or_create(
            code="CCS", defaults={"name": "College of Computer Studies"}
        )
        College.objects.get_or_create(
            code="CBA", defaults={"name": "College of Business and Accountancy"}
        )
        self.ccs_faculty = self.make_faculty("ccs-faculty", "CCS")
        self.cba_faculty = self.make_faculty("cba-faculty", "CBA")
        self.student_a = self.make_student("student-a")
        self.student_b = self.make_student("student-b")
        self.period_start = date(2026, 1, 1)
        self.period_end = date(2026, 1, 31)

    def make_student(self, username, college="CCS"):
        return get_user_model().objects.create(
            username=username,
            role="student",
            account_status="active",
            college=college,
        )

    def make_faculty(
        self,
        username,
        college,
        current_status="available",
        account_status="active",
    ):
        user = get_user_model().objects.create(
            username=username,
            role="faculty",
            account_status=account_status,
            college=college,
        )
        return FacultyProfile.objects.create(
            faculty_id=f"faculty-{username}",
            user=user,
            college_id=college,
            current_status=current_status,
            manual_status=current_status,
        )

    def make_consultation(
        self,
        identifier,
        *,
        faculty=None,
        student=None,
        scheduled_date=date(2026, 1, 12),
        start_hour=10,
        status="pending",
        agenda="general_concern",
        requested_at=None,
        approved_at=None,
    ):
        consultation = ConsultationRequest.objects.create(
            request_id=identifier,
            user=student or self.student_a,
            faculty=faculty or self.ccs_faculty,
            date=scheduled_date,
            start_time=datetime.min.time().replace(hour=start_hour),
            end_time=datetime.min.time().replace(hour=(start_hour + 1) % 24),
            status=status,
            agenda=agenda,
            approved_at=approved_at,
        )
        if requested_at is not None:
            ConsultationRequest.objects.filter(pk=consultation.pk).update(
                requested_at=requested_at
            )
            consultation.refresh_from_db()
        return consultation

    def analytics(self, college="CCS", start=None, end=None):
        return get_college_analytics(
            college,
            start or self.period_start,
            end or self.period_end,
        )

    def test_college_analytics_isolation(self):
        self.make_consultation("ccs-request", status="completed")
        self.make_consultation(
            "cba-request",
            faculty=self.cba_faculty,
            student=self.student_b,
            status="completed",
        )
        local_tz = ZoneInfo("Asia/Manila")
        WalkInQueue.objects.create(
            queue_id="ccs-walk-in",
            faculty=self.ccs_faculty,
            user=self.student_a,
            position=1,
            status="completed",
            joined_at=datetime(2026, 1, 10, 9, tzinfo=local_tz),
            served_at=datetime(2026, 1, 10, 9, 30, tzinfo=local_tz),
        )
        WalkInQueue.objects.create(
            queue_id="cba-walk-in",
            faculty=self.cba_faculty,
            user=self.student_b,
            position=1,
            status="completed",
            joined_at=datetime(2026, 1, 10, 9, tzinfo=local_tz),
            served_at=datetime(2026, 1, 10, 9, 30, tzinfo=local_tz),
        )
        StatusHistory.objects.create(
            history_id="ccs-history",
            faculty=self.ccs_faculty,
            status="available",
            changed_at=datetime(2025, 12, 31, 15, tzinfo=UTC),
        )
        StatusHistory.objects.create(
            history_id="cba-history",
            faculty=self.cba_faculty,
            status="available",
            changed_at=datetime(2025, 12, 31, 15, tzinfo=UTC),
        )

        result = self.analytics()

        self.assertEqual(result["consultations"]["total_records"], 1)
        self.assertEqual(result["walk_ins"]["total"], 1)
        self.assertEqual(result["faculty_availability"]["current"]["total_active_faculty"], 1)
        self.assertEqual(result["faculty_availability"]["historical_proxy"]["faculty_with_history"], 1)
        self.assertEqual(len(result["faculty_workload"]["items"]), 1)
        self.assertEqual(
            result["faculty_workload"]["items"][0]["faculty_key"],
            f"faculty:{self.ccs_faculty.faculty_id}",
        )

    def test_consultation_summary_status_distribution(self):
        for index, status in enumerate(ConsultationRequest.STATUS_CHOICES):
            self.make_consultation(f"status-{index}", status=status[0])

        distribution = self.analytics()["consultations"]["status_distribution"]

        self.assertEqual(distribution, {
            "pending": 1,
            "approved": 1,
            "declined": 1,
            "cancelled": 1,
            "completed": 1,
        })

    def test_consultation_summary_agenda_distribution(self):
        for index, agenda in enumerate(ConsultationRequest.AGENDA_CHOICES):
            self.make_consultation(f"agenda-{index}", agenda=agenda[0])

        distribution = self.analytics()["consultations"]["agenda_distribution"]

        self.assertEqual(distribution, {
            "grade_consultation": 1,
            "project_consultation": 1,
            "general_concern": 1,
            "academic_advising": 1,
        })

    def test_overall_completion_rate(self):
        for index in range(5):
            self.make_consultation(f"completed-{index}", status="completed")
        for index in range(3):
            self.make_consultation(f"pending-{index}", status="pending")

        completion = self.analytics()["consultations"]["completion"]

        self.assertEqual(completion["completed_count"], 5)
        self.assertEqual(completion["overall_denominator"], 8)
        self.assertEqual(completion["overall_rate_percent"], 62.5)

    def test_resolved_completion_rate_excludes_open_requests(self):
        statuses = ["completed"] * 5 + ["declined"] * 2 + ["cancelled", "pending", "approved"]
        for index, status in enumerate(statuses):
            self.make_consultation(f"resolved-{index}", status=status)

        completion = self.analytics()["consultations"]["completion"]

        self.assertEqual(completion["resolved_denominator"], 8)
        self.assertEqual(completion["resolved_rate_percent"], 62.5)

    def test_zero_denominators_return_none(self):
        College.objects.create(code="EMPTY", name="Empty College")

        result = self.analytics("EMPTY")

        self.assertIsNone(result["consultations"]["completion"]["overall_rate_percent"])
        self.assertIsNone(result["consultations"]["completion"]["resolved_rate_percent"])
        self.assertIsNone(result["faculty_availability"]["current"]["availability_rate_percent"])
        self.assertIsNone(result["student_behavior"]["repeat_student_rate_percent"])
        self.assertIsNone(result["student_behavior"]["average_requests_per_student"])

    def test_peak_completed_hour_excludes_noncompleted_requests(self):
        self.make_consultation("completed-10-a", status="completed", start_hour=10)
        self.make_consultation("completed-10-b", status="completed", start_hour=10)
        for index, status in enumerate(("pending", "declined", "cancelled")):
            self.make_consultation(
                f"excluded-14-{index}", status=status, start_hour=14
            )

        peak = self.analytics()["consultation_patterns"]["peak_hour"]

        self.assertEqual(peak, {"hours": [10], "count": 2})

    def test_peak_hour_returns_all_ties(self):
        for index in range(3):
            self.make_consultation(f"tie-10-{index}", status="completed", start_hour=10)
            self.make_consultation(f"tie-14-{index}", status="completed", start_hour=14)

        peak = self.analytics()["consultation_patterns"]["peak_hour"]

        self.assertEqual(peak, {"hours": [10, 14], "count": 3})

    def test_peak_completed_hour_includes_8pm(self):
        self.make_consultation("eight-pm", status="completed", start_hour=20)

        patterns = self.analytics()["consultation_patterns"]

        self.assertEqual(patterns["peak_hour"], {"hours": [20], "count": 1})
        self.assertEqual(patterns["hourly_distribution"][20], {"hour": 20, "count": 1})

    def test_peak_completed_weekday_uses_readable_name(self):
        monday = date(2026, 1, 5)
        tuesday = date(2026, 1, 6)
        self.make_consultation("monday-a", status="completed", scheduled_date=monday)
        self.make_consultation("monday-b", status="completed", scheduled_date=monday)
        self.make_consultation("tuesday", status="completed", scheduled_date=tuesday)

        peak = self.analytics()["consultation_patterns"]["peak_weekday"]

        self.assertEqual(peak, {"weekdays": ["Monday"], "count": 2})

    def test_peak_weekday_returns_all_ties(self):
        self.make_consultation("monday", status="completed", scheduled_date=date(2026, 1, 5))
        self.make_consultation("tuesday", status="completed", scheduled_date=date(2026, 1, 6))

        peak = self.analytics()["consultation_patterns"]["peak_weekday"]

        self.assertEqual(peak, {"weekdays": ["Monday", "Tuesday"], "count": 1})

    def test_request_submission_hour_uses_manila_timezone(self):
        requested_at = datetime(2026, 1, 1, 16, 30, tzinfo=UTC)
        self.make_consultation(
            "timezone-request",
            scheduled_date=date(2026, 1, 20),
            start_hour=14,
            requested_at=requested_at,
        )
        period = normalize_period(date(2026, 1, 2), date(2026, 1, 2))

        patterns = get_request_submission_patterns("CCS", period)

        self.assertEqual(patterns["total_submitted"], 1)
        self.assertEqual(patterns["peak_hour"], {"hours": [0], "count": 1})
        self.assertEqual(patterns["peak_weekday"], {"weekdays": ["Friday"], "count": 1})

    def test_request_patterns_use_requested_at_not_scheduled_date(self):
        requested_monday = datetime(2026, 1, 5, 1, 0, tzinfo=UTC)  # Monday 09:00 Manila
        for index in range(2):
            self.make_consultation(
                f"submitted-monday-{index}",
                scheduled_date=date(2026, 1, 6),
                start_hour=14,
                requested_at=requested_monday + timedelta(minutes=index),
            )
        period = normalize_period(date(2026, 1, 5), date(2026, 1, 6))

        patterns = get_request_submission_patterns("CCS", period)

        self.assertEqual(patterns["peak_hour"], {"hours": [9], "count": 2})
        self.assertEqual(patterns["peak_weekday"], {"weekdays": ["Monday"], "count": 2})
        self.assertEqual(patterns["peak_weekday_hour"]["combinations"], [{
            "weekday": "Monday",
            "hour": 9,
            "label": "Monday 09:00",
        }])

    def test_request_peak_combination_returns_ties(self):
        timestamps = [
            datetime(2026, 1, 5, 1, 0, tzinfo=UTC),
            datetime(2026, 1, 6, 6, 0, tzinfo=UTC),
        ]
        for index, timestamp in enumerate(timestamps):
            self.make_consultation(f"combo-{index}", requested_at=timestamp)
        period = normalize_period(date(2026, 1, 5), date(2026, 1, 6))

        patterns = get_request_submission_patterns("CCS", period)

        self.assertEqual(patterns["peak_weekday_hour"]["count"], 1)
        self.assertEqual(len(patterns["peak_weekday_hour"]["combinations"]), 2)

    def test_current_availability_counts_only_available_status(self):
        College.objects.create(code="AV", name="Availability College")
        for status in ("available", "busy", "virtual_only", "on_leave", "unavailable"):
            self.make_faculty(f"av-{status}", "AV", current_status=status)

        availability = get_current_availability("AV")

        self.assertEqual(availability["total_active_faculty"], 5)
        self.assertEqual(availability["available_count"], 1)
        self.assertEqual(availability["availability_rate_percent"], 20.0)
        self.assertFalse(availability["virtual_only_included_in_available"])

    def test_current_availability_excludes_inactive_faculty(self):
        College.objects.create(code="ACTIVE", name="Active College")
        self.make_faculty("active-available", "ACTIVE", current_status="available")
        self.make_faculty(
            "inactive-available",
            "ACTIVE",
            current_status="available",
            account_status="deactivated",
        )

        availability = get_current_availability("ACTIVE")

        self.assertEqual(availability["total_active_faculty"], 1)
        self.assertEqual(availability["availability_rate_percent"], 100.0)

    def test_historical_availability_is_faculty_time_weighted(self):
        College.objects.create(code="HIST", name="History College")
        faculty = self.make_faculty("history", "HIST")
        StatusHistory.objects.create(
            history_id="history-carry",
            faculty=faculty,
            status="available",
            changed_at=datetime(2025, 12, 31, 15, tzinfo=UTC),
        )
        StatusHistory.objects.create(
            history_id="history-noon",
            faculty=faculty,
            status="busy",
            changed_at=datetime(2026, 1, 1, 4, tzinfo=UTC),
        )
        period = normalize_period(date(2026, 1, 1), date(2026, 1, 1))

        availability = get_historical_availability_proxy("HIST", period)

        self.assertTrue(availability["calculable"])
        self.assertEqual(availability["rate_percent"], 50.0)
        self.assertEqual(availability["available_seconds"], 12 * 60 * 60)
        self.assertEqual(availability["observed_faculty_seconds"], 24 * 60 * 60)

    def test_historical_availability_tracks_partial_coverage(self):
        College.objects.create(code="PART", name="Partial History College")
        with_history = self.make_faculty("partial-history", "PART")
        self.make_faculty("no-history", "PART")
        StatusHistory.objects.create(
            history_id="partial-row",
            faculty=with_history,
            status="available",
            changed_at=datetime(2026, 1, 1, 4, tzinfo=UTC),
        )
        period = normalize_period(date(2026, 1, 1), date(2026, 1, 1))

        availability = get_historical_availability_proxy("PART", period)

        self.assertEqual(availability["rate_percent"], 100.0)
        self.assertEqual(availability["faculty_with_history"], 1)
        self.assertEqual(availability["faculty_without_history"], 1)
        self.assertEqual(availability["partial_history_faculty"], 1)
        self.assertEqual(availability["coverage_percent"], 50.0)
        self.assertEqual(availability["observation_coverage_percent"], 25.0)

    def test_historical_availability_unknown_is_not_zero(self):
        College.objects.create(code="NOHIST", name="No History College")
        self.make_faculty("no-history-only", "NOHIST")
        period = normalize_period(date(2026, 1, 1), date(2026, 1, 1))

        availability = get_historical_availability_proxy("NOHIST", period)

        self.assertFalse(availability["calculable"])
        self.assertIsNone(availability["rate_percent"])

    def test_student_repeat_rate_and_average_requests(self):
        student_c = self.make_student("student-c")
        for index in range(3):
            self.make_consultation(f"student-a-{index}", student=self.student_a)
        self.make_consultation("student-b", student=self.student_b)
        for index in range(2):
            self.make_consultation(f"student-c-{index}", student=student_c)

        behavior = self.analytics()["student_behavior"]

        self.assertEqual(behavior["unique_students"], 3)
        self.assertEqual(behavior["repeat_students"], 2)
        self.assertEqual(behavior["repeat_student_rate_percent"], 66.67)
        self.assertEqual(behavior["average_requests_per_student"], 2.0)
        self.assertNotIn("name", json.dumps(behavior).lower())

    def test_faculty_workload_contains_all_status_counts_without_names(self):
        for index, status in enumerate(("pending", "approved", "declined", "cancelled", "completed")):
            self.make_consultation(f"workload-{index}", status=status)

        workload = self.analytics()["faculty_workload"]["items"][0]

        self.assertEqual(workload["total_requests"], 5)
        self.assertEqual(workload["completed_requests"], 1)
        self.assertEqual(workload["completion_rate_percent"], 20.0)
        self.assertNotIn("name", workload)
        self.assertNotIn("email", workload)

    def test_walk_in_status_distribution_and_resolved_rate(self):
        local_tz = ZoneInfo("Asia/Manila")
        statuses = ["completed"] * 3 + ["cancelled"] + ["waiting"] * 2 + ["called"]
        for index, status in enumerate(statuses):
            WalkInQueue.objects.create(
                queue_id=f"walk-status-{index}",
                faculty=self.ccs_faculty,
                user=self.student_a,
                position=index + 1,
                status=status,
                joined_at=datetime(2026, 1, 10, 9 + index, tzinfo=local_tz),
            )

        walk_ins = self.analytics()["walk_ins"]

        self.assertEqual(walk_ins["status_distribution"], {
            "waiting": 2,
            "called": 1,
            "completed": 3,
            "cancelled": 1,
        })
        self.assertEqual(walk_ins["resolved_denominator"], 4)
        self.assertEqual(walk_ins["resolved_completion_rate_percent"], 75.0)

    def test_walk_in_timing_proxy_handles_missing_notified_at(self):
        local_tz = ZoneInfo("Asia/Manila")
        joined = datetime(2026, 1, 10, 9, tzinfo=local_tz)
        WalkInQueue.objects.create(
            queue_id="walk-timed",
            faculty=self.ccs_faculty,
            user=self.student_a,
            position=1,
            status="completed",
            joined_at=joined,
            notified_at=joined + timedelta(minutes=10),
            served_at=joined + timedelta(minutes=40),
        )
        WalkInQueue.objects.create(
            queue_id="walk-no-notification",
            faculty=self.ccs_faculty,
            user=self.student_b,
            position=2,
            status="completed",
            joined_at=joined + timedelta(hours=1),
            served_at=joined + timedelta(hours=1, minutes=20),
        )

        timing = self.analytics()["walk_ins"]["timing"]

        self.assertTrue(timing["timing_is_proxy"])
        self.assertEqual(timing["average_join_to_notification_minutes"], 10.0)
        self.assertEqual(timing["join_to_notification_sample_size"], 1)
        self.assertEqual(timing["average_join_to_completion_minutes"], 30.0)
        self.assertEqual(timing["join_to_completion_sample_size"], 2)
        self.assertEqual(timing["average_notification_to_completion_minutes"], 30.0)
        self.assertEqual(timing["missing_notified_at_count"], 1)

    def test_period_filtering_uses_inclusive_scheduled_dates(self):
        self.make_consultation("before", scheduled_date=date(2025, 12, 31))
        self.make_consultation("inside-start", scheduled_date=date(2026, 1, 1))
        self.make_consultation("inside-end", scheduled_date=date(2026, 1, 31))
        self.make_consultation("after", scheduled_date=date(2026, 2, 1))

        result = self.analytics()

        self.assertEqual(result["consultations"]["total_records"], 2)

    def test_equal_period_comparison_uses_same_duration(self):
        for index in range(2):
            self.make_consultation(
                f"previous-{index}", scheduled_date=date(2026, 1, 1 + index)
            )
        for index in range(3):
            self.make_consultation(
                f"current-{index}", scheduled_date=date(2026, 1, 8 + index)
            )

        trends = self.analytics(start=date(2026, 1, 8), end=date(2026, 1, 14))["trends"]

        self.assertEqual(trends["current_period_count"], 3)
        self.assertEqual(trends["previous_period_count"], 2)
        self.assertEqual(trends["growth_percent"], 50.0)
        self.assertEqual(trends["comparison_period"]["duration_days"], 7)
        self.assertTrue(trends["growth_comparable"])

    def test_empty_college_returns_complete_json_safe_payload(self):
        College.objects.create(code="EMPTYJSON", name="Empty JSON College")

        result = self.analytics("EMPTYJSON")

        serialized = json.dumps(result)
        self.assertTrue(serialized)
        self.assertEqual(result["schema_version"], "1.0")
        self.assertEqual(result["data_quality"]["confidence"], "low")
        self.assertFalse(result["capacity"]["authoritatively_calculable"])
        self.assertIsNone(result["capacity"]["supply_demand_gap"])
