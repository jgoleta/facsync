import csv
import io
from datetime import date
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from apps.faculty.models import FacultyProfile
from apps.faculty.services.calendar_events import serialize_schedule_event
from apps.faculty.services.google_calendar import google_event_payload


class CsvUploadRegressionTests(TestCase):
    def setUp(self):
        self.faculty_user = get_user_model().objects.create_user(username='csv-faculty', role='faculty', college='CCS')
        self.head = get_user_model().objects.create_user(username='csv-head', role='depthead', college='CCS')
        self.faculty = FacultyProfile.objects.create(user=self.faculty_user, faculty_id='csv-faculty', college_id='CCS')

    def template(self, head=False):
        self.client.force_login(self.head if head else self.faculty_user)
        response = self.client.get(reverse('depthead:faculty_schedule_template' if head else 'faculty:schedule_template'))
        self.assertEqual(response.status_code, 200)
        return list(csv.reader(io.StringIO(response.content.decode())))

    def upload(self, rows, head=False):
        output = io.StringIO()
        csv.writer(output).writerows(rows)
        upload = SimpleUploadedFile('schedule.csv', output.getvalue().encode(), content_type='text/csv')
        url = reverse('depthead:upload_faculty_schedule', args=[self.faculty.pk]) if head else reverse('faculty:upload_schedule')
        with patch('apps.depthead.views.send_schedule_uploaded_email', return_value=False):
            return self.client.post(url, {'file': upload})

    def test_both_downloaded_templates_upload_successfully(self):
        for head in (False, True):
            with self.subTest(head=head):
                rows = self.template(head)
                self.assertTrue(all(len(row) == len(rows[0]) for row in rows))
                response = self.upload(rows, head)
                self.assertEqual(response.status_code, 201, response.content)
                self.assertEqual(response.json()['added_count'], 2)

    def test_supported_dates_and_blank_room_upload(self):
        for head in (False, True):
            for start, end in [('2026-08-17', '2026-12-15'), ('08/17/2026', '12/15/2026'), ('08-17-2026', '12-15-2026')]:
                with self.subTest(head=head, start=start):
                    rows = self.template(head)[:2]
                    rows[1][8:10] = [start, end]
                    rows[1][-1] = ''
                    response = self.upload(rows, head)
                    self.assertEqual(response.status_code, 201, response.content)

    def test_overlapping_rows_return_validation_error_not_server_error(self):
        rows = self.template()
        rows[2] = list(rows[1])
        rows[2][0] = 'OTHER-OFFERING'
        response = self.upload(rows)
        self.assertEqual(response.status_code, 400)
        self.assertIn('Overlaps', ' '.join(response.json()['errors']))
        self.assertFalse(self.faculty.schedule_events.exists())

    def test_same_time_on_different_weekdays_is_allowed(self):
        rows = self.template()
        rows[2] = list(rows[1])
        rows[2][0] = 'OTHER-OFFERING'
        rows[2][7] = 'Tuesday'
        response = self.upload(rows)
        self.assertEqual(response.status_code, 201, response.content)

    def test_invalid_date_is_a_validation_error(self):
        rows = self.template()
        rows[1][8] = '2026-02-30'
        response = self.upload(rows)
        self.assertEqual(response.status_code, 400)
        self.assertIn('DAYFROM', ' '.join(response.json()['errors']))

    def test_recurring_uploads_preserve_weekday_and_date_bounds_for_both_roles(self):
        for head in (False, True):
            with self.subTest(head=head):
                rows = self.template(head)[:2]
                rows[1][7:10] = ['Monday', '2026-09-30', '2026-10-20']
                response = self.upload(rows, head)
                self.assertEqual(response.status_code, 201, response.content)
                event = self.faculty.schedule_events.order_by('-pk').first()
                self.assertIsNone(event.date)
                self.assertEqual(event.day_of_week, 'monday')
                self.assertEqual((event.start_month, event.end_month), (9, 10))
                self.assertEqual(event.recurrence_start_date, date(2026, 9, 30))
                self.assertEqual(event.recurrence_end_date, date(2026, 10, 20))
                calendar = serialize_schedule_event(event)
                self.assertTrue(calendar['is_recurring'])
                self.assertEqual(calendar['recurrence_end_date'], '2026-10-20')
                google = google_event_payload(event)
                self.assertEqual(google['recurrence'], ['RRULE:FREQ=WEEKLY;BYDAY=MO;COUNT=3'])
                self.assertTrue(google['start']['dateTime'].startswith('2026-10-05'))
