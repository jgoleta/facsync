import json

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from apps.faculty.models import FacultyProfile, ScheduleEvent


class UnifiedPreviewTests(TestCase):
    def setUp(self):
        users = get_user_model().objects
        self.user = users.create_user(username='faculty-preview', role='faculty', college='CCS')
        self.head = users.create_user(username='college-head-preview', role='depthead', college='CCS')
        self.faculty = FacultyProfile.objects.create(user=self.user, faculty_id='preview', college_id='CCS')
        self.client.force_login(self.user)

    def upload(self, url):
        csv = SimpleUploadedFile('schedule.csv',
            b'event_title,short_description,room_location,recurring_day,start_month,end_month,start_time,end_time,status_type\n'
            b'Office hours,Consultations,Room 1,Monday,8,5,09:00,10:00,Busy\n')
        response = self.client.post(url, {'file': csv})
        self.assertEqual(response.status_code, 201)

    def test_mixed_uploads_append_preview_and_delete_only_displayed_rows(self):
        legacy = ScheduleEvent.objects.create(faculty=self.faculty, title='Legacy', managed_by_facsync=True)
        external = ScheduleEvent.objects.create(faculty=self.faculty, title='External', managed_by_facsync=False)
        self.client.force_login(self.head)
        self.upload(reverse('depthead:upload_faculty_schedule', args=[self.faculty.faculty_id]))
        self.client.force_login(self.user)
        self.upload(reverse('faculty:upload_schedule'))
        self.upload(reverse('faculty:upload_schedule'))
        self.assertEqual(self.faculty.schedule_events.count(), 5)
        self.assertEqual(self.faculty.schedule_events.filter(uploaded_by=self.head).count(), 1)
        self.assertEqual(self.faculty.schedule_events.filter(uploaded_by=self.user).count(), 2)
        response = self.client.get(reverse('faculty:view_schedule_preview'))
        self.assertEqual(response.status_code, 200)
        rows = response.json()['preview']
        self.assertEqual(len(rows), 4)
        self.assertEqual(rows[0]['id'], legacy.pk)
        self.assertEqual(rows[0]['uploader_label'], 'Uploader unknown')
        self.assertEqual(rows[1]['uploader_label'], 'Uploaded by college-head-preview')
        self.assertTrue(rows[1]['uploaded_by_other'])
        self.assertEqual(rows[2]['uploader_label'], 'Uploaded by you')
        self.assertFalse(rows[2]['uploaded_by_other'])
        self.client.force_login(self.head)
        head_rows = self.client.get(reverse('depthead:view_faculty_schedule_preview', args=[self.faculty.faculty_id])).json()['preview']
        self.assertEqual([{k: v for k, v in row.items() if k not in ('id', 'uploader_label', 'uploaded_by_other')} for row in rows], head_rows)
        self.client.force_login(self.user)
        other_user = get_user_model().objects.create_user(username='other', role='faculty')
        other_faculty = FacultyProfile.objects.create(user=other_user, faculty_id='other', college_id='CCS')
        other_event = ScheduleEvent.objects.create(faculty=other_faculty, title='Private', managed_by_facsync=True)
        self.assertEqual(len(self.client.get(reverse('faculty:view_schedule_preview')).json()['preview']), 4)
        response = self.client.post(reverse('faculty:clear_schedule'),
            data=json.dumps({'event_ids': [r['id'] for r in rows] + [external.pk, other_event.pk]}), content_type='application/json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['deleted_count'], 4)
        self.assertTrue(ScheduleEvent.objects.filter(pk=external.pk).exists())
        self.assertTrue(ScheduleEvent.objects.filter(pk=other_event.pk).exists())

    def test_access_and_missing_profile(self):
        self.assertEqual(self.client.post(reverse('faculty:view_schedule_preview')).status_code, 405)
        self.client.force_login(self.head)
        self.assertEqual(self.client.get(reverse('faculty:view_schedule_preview')).status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.get(reverse('faculty:view_schedule_preview')).status_code, 302)

    def test_deleted_uploader_preserves_schedule(self):
        event = ScheduleEvent.objects.create(faculty=self.faculty, title='Retained', uploaded_by=self.head, managed_by_facsync=True)
        self.head.delete()
        event.refresh_from_db()
        self.assertIsNone(event.uploaded_by_id)
