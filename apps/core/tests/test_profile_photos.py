from io import BytesIO
from types import SimpleNamespace
from unittest.mock import Mock, patch

from PIL import Image
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import DatabaseError
from django.test import Client, RequestFactory, SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from apps.core.adapters import FacSyncSocialAdapter
from apps.core.models import DeptHeadInvite, FacultyInvite, User
from apps.core.profile_photos import (
    MAX_PHOTO_BYTES, PhotoStorage, PhotoStorageError, normalize_photo, safe_photo_url,
)
from apps.faculty.models import FacultyProfile


GOOGLE = 'https://lh3.googleusercontent.com/test-photo'
UPLOAD = 'https://project.supabase.co/storage/v1/object/public/faculty-photos/1/' + 'a' * 32 + '.webp'
STORAGE = dict(SUPABASE_URL='https://project.supabase.co', SUPABASE_SECRET_KEY='sb_secret_test',
               SUPABASE_FACULTY_PHOTO_BUCKET='faculty-photos', SUPABASE_STUDENT_PHOTO_BUCKET='student-photos')


def image_upload(fmt='PNG', size=(24, 24)):
    data = BytesIO()
    Image.new('RGB', size, 'blue').save(data, format=fmt)
    extension, mime = {'PNG': ('png', 'image/png'), 'JPEG': ('jpg', 'image/jpeg'), 'WEBP': ('webp', 'image/webp')}[fmt]
    return SimpleUploadedFile(f'photo.{extension}', data.getvalue(), content_type=mime)


class PhotoValidationTests(SimpleTestCase):
    def test_supported_formats_decode_to_small_webp(self):
        for fmt in ['JPEG', 'PNG', 'WEBP']:
            with self.subTest(fmt=fmt):
                image = Image.open(BytesIO(normalize_photo(image_upload(fmt, (900, 700)))))
                self.assertEqual(image.format, 'WEBP')
                self.assertLessEqual(max(image.size), 512)
                self.assertFalse(image.getexif())

    def test_reject_missing_file(self):
        with self.assertRaises(ValidationError):
            normalize_photo(None)

    def test_reject_bad_extension_mime_and_content(self):
        for file in [SimpleUploadedFile('a.svg', b'<svg/>', content_type='image/svg+xml'),
                     SimpleUploadedFile('a.png', b'not an image', content_type='image/png'),
                     SimpleUploadedFile('a.png', b'x', content_type='text/html')]:
            with self.subTest(name=file.name), self.assertRaises(ValidationError):
                normalize_photo(file)

    def test_reject_disguised_file(self):
        file = image_upload('JPEG')
        file.name, file.content_type = 'a.png', 'image/png'
        with self.assertRaises(ValidationError):
            normalize_photo(file)

    def test_reject_oversized(self):
        with self.assertRaises(ValidationError):
            normalize_photo(SimpleUploadedFile('a.png', b'x' * (MAX_PHOTO_BYTES + 1), content_type='image/png'))

    def test_reject_excessive_pixels(self):
        with patch('apps.core.profile_photos.MAX_PHOTO_PIXELS', 100):
            with self.assertRaises(ValidationError):
                normalize_photo(image_upload())

    def test_reject_animated_image(self):
        data = BytesIO()
        Image.new('RGB', (10, 10), 'blue').save(data, format='WEBP', save_all=True,
                                              append_images=[Image.new('RGB', (10, 10), 'red')])
        with self.assertRaises(ValidationError):
            normalize_photo(SimpleUploadedFile('a.webp', data.getvalue(), content_type='image/webp'))

    def test_reencoding_removes_metadata(self):
        data = BytesIO()
        image = Image.new('RGB', (24, 24))
        exif = image.getexif()
        exif[270] = 'private information'
        image.save(data, format='JPEG', exif=exif)
        clean = normalize_photo(SimpleUploadedFile('a.jpg', data.getvalue(), content_type='image/jpeg'))
        self.assertNotIn(b'private information', clean)
        self.assertFalse(Image.open(BytesIO(clean)).getexif())

    def test_reject_unsafe_photo_urls(self):
        for value in [None, 'javascript:alert(1)', 'http://example.com/a', '//example.com/a', 'https://user:pass@example.com/a']:
            self.assertEqual(safe_photo_url(value), '')


class PhotoAccountTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='photo-student', role='student', google_photo_url=GOOGLE)
        self.client.force_login(self.user)
        self.url = reverse('core:profile_photo')

    def test_fallback_precedence(self):
        faculty = User(role='faculty', username='abc', google_photo_url=GOOGLE, uploaded_photo_url=UPLOAD)
        self.assertEqual(faculty.avatar_url, UPLOAD)
        faculty.uploaded_photo_url = ''
        self.assertEqual(faculty.avatar_url, GOOGLE)
        faculty.google_photo_url = ''
        self.assertEqual(faculty.avatar_url, '')
        self.assertEqual(faculty.avatar_initials, 'A')

    def test_student_upload_resolves_to_owner_endpoint(self):
        self.user.uploaded_photo_url = 'https://project.supabase.co/storage/v1/object/authenticated/student-photos/private'
        self.assertEqual(self.user.avatar_url, reverse('core:profile_photo_image', args=[self.user.pk]))
        self.assertNotIn('supabase', self.user.avatar_url)

    def test_upload_does_not_replace_google_photo_or_another_user(self):
        other = User.objects.create_user(username='other', role='student')
        with patch('apps.core.photo_views.PhotoStorage') as storage:
            storage.return_value.upload.return_value = 'https://project.supabase.co/private.webp'
            response = self.client.post(self.url, {'action': 'upload', 'photo': image_upload(), 'user_id': other.pk})
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        other.refresh_from_db()
        self.assertEqual(self.user.google_photo_url, GOOGLE)
        self.assertTrue(self.user.uploaded_photo_url)
        self.assertFalse(other.uploaded_photo_url)

    def test_invalid_upload_never_calls_storage(self):
        with patch('apps.core.photo_views.PhotoStorage') as storage:
            response = self.client.post(self.url, {'action': 'upload', 'photo': SimpleUploadedFile('a.svg', b'<svg/>')})
        self.assertEqual(response.status_code, 400)
        storage.assert_not_called()

    def test_remove_reverts_to_google_and_cleans_after_commit(self):
        self.user.uploaded_photo_url = UPLOAD
        self.user.save()
        with patch('apps.core.photo_views.delete_photo_safely') as cleanup:
            with self.captureOnCommitCallbacks(execute=True):
                response = self.client.post(self.url, {'action': 'remove'})
            cleanup.assert_called_once_with(self.user.pk, UPLOAD)
        self.assertEqual(response.json()['avatar_url'], GOOGLE)
        self.user.refresh_from_db()
        self.assertEqual(self.user.uploaded_photo_url, '')

    def test_replacement_cleans_previous_url(self):
        self.user.uploaded_photo_url = UPLOAD
        self.user.save()
        with patch('apps.core.photo_views.PhotoStorage') as storage, patch('apps.core.photo_views.delete_photo_safely') as cleanup:
            storage.return_value.upload.return_value = 'https://example.com/new.webp'
            with self.captureOnCommitCallbacks(execute=True):
                self.client.post(self.url, {'action': 'upload', 'photo': image_upload()})
            cleanup.assert_called_once_with(self.user.pk, UPLOAD)

    def test_storage_failure_keeps_existing_photo(self):
        self.user.uploaded_photo_url = UPLOAD
        self.user.save()
        with patch('apps.core.photo_views.PhotoStorage', side_effect=PhotoStorageError('Storage unavailable')):
            response = self.client.post(self.url, {'action': 'upload', 'photo': image_upload()})
        self.assertEqual(response.status_code, 503)
        self.user.refresh_from_db()
        self.assertEqual(self.user.uploaded_photo_url, UPLOAD)

    def test_database_failure_cleans_new_object(self):
        with patch('apps.core.photo_views.PhotoStorage') as storage, patch('apps.core.photo_views.delete_photo_safely') as cleanup:
            storage.return_value.upload.return_value = UPLOAD
            with patch.object(User, 'save', side_effect=DatabaseError('test')):
                with self.assertRaises(DatabaseError):
                    self.client.post(self.url, {'action': 'upload', 'photo': image_upload()})
            cleanup.assert_called_once_with(self.user.pk, UPLOAD)

    def test_upload_requires_login_role_and_csrf(self):
        self.assertEqual(Client().post(self.url, {'action': 'remove'}).status_code, 302)
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.user)
        self.assertEqual(csrf_client.post(self.url, {'action': 'remove'}).status_code, 403)
        for role in ['depthead', 'superadmin']:
            self.user.role = role
            self.user.save()
            self.assertEqual(self.client.post(self.url, {'action': 'remove'}).status_code, 403)

    def test_deactivated_user_cannot_change_photo(self):
        self.user.account_status = 'deactivated'
        self.user.save()
        self.assertEqual(self.client.post(self.url, {'action': 'remove'}).status_code, 403)

    def test_private_photo_is_owner_only_and_not_cached(self):
        self.user.uploaded_photo_url = 'https://example.com/private'
        self.user.save()
        url = reverse('core:profile_photo_image', args=[self.user.pk])
        with patch('apps.core.photo_views.PhotoStorage') as storage:
            storage.return_value.signed_student_url.return_value = 'https://project.supabase.co/signed?token=example'
            response = self.client.get(url)
            self.assertEqual(response.status_code, 302)
            self.assertIn('no-store', response['Cache-Control'])
            self.assertEqual(response['Referrer-Policy'], 'no-referrer')
            storage.reset_mock()
            other = User.objects.create_user(username='different', role='student')
            self.client.force_login(other)
            self.assertEqual(self.client.get(url).status_code, 403)
            self.assertEqual(Client().get(url).status_code, 403)
            storage.assert_not_called()

    def test_account_delete_cleans_upload_after_commit(self):
        self.user.uploaded_photo_url = UPLOAD
        self.user.save()
        user_id = self.user.pk
        with patch('apps.core.profile_photos.delete_photo_safely') as cleanup:
            with self.captureOnCommitCallbacks(execute=True):
                self.user.delete()
            cleanup.assert_called_once_with(user_id, UPLOAD)

    def test_google_photo_updates_without_overwriting_upload(self):
        self.user.uploaded_photo_url = UPLOAD
        self.user.save()
        login = SimpleNamespace(is_existing=True, user=self.user,
                                account=SimpleNamespace(provider='google', extra_data={'picture': GOOGLE + '-new'}))
        FacSyncSocialAdapter().pre_social_login(RequestFactory().get('/'), login)
        self.user.refresh_from_db()
        self.assertEqual(self.user.google_photo_url, GOOGLE + '-new')
        self.assertEqual(self.user.uploaded_photo_url, UPLOAD)

    def test_student_and_invited_roles_capture_google_photo_at_signup(self):
        for role in ['student', 'faculty', 'depthead']:
            with self.subTest(role=role):
                email = f'{role}@example.com'
                request = RequestFactory().get('/')
                request.session = {'registration_role': 'student'} if role == 'student' else {}
                if role == 'faculty':
                    FacultyInvite.objects.create(email=email, college='CCS')
                if role == 'depthead':
                    DeptHeadInvite.objects.create(email=email, college='CCS')
                user = User(username=f'new-{role}')
                login = SimpleNamespace(is_existing=False, user=user,
                                        account=SimpleNamespace(provider='google', extra_data={'email': email, 'picture': GOOGLE}))
                adapter = FacSyncSocialAdapter()
                adapter.pre_social_login(request, login)
                def persist(request, sociallogin, form):
                    sociallogin.user.save()
                    return sociallogin.user
                with patch.object(DefaultSocialAccountAdapter, 'save_user', side_effect=persist):
                    adapter.save_user(request, login)
                user.refresh_from_db()
                self.assertEqual(user.role, role)
                self.assertEqual(user.google_photo_url, GOOGLE)

    def test_missing_google_photo_does_not_block_signup(self):
        user = User(username='without-photo', role='student')
        login = SimpleNamespace(user=user, account=SimpleNamespace(provider='google', extra_data={}))
        with patch.object(DefaultSocialAccountAdapter, 'save_user', return_value=user):
            self.assertIs(FacSyncSocialAdapter().save_user(RequestFactory().get('/'), login), user)
        self.assertEqual(user.google_photo_url, '')


@override_settings(**STORAGE)
class PhotoStorageTests(SimpleTestCase):
    def setUp(self):
        self.user = User(pk=1, role='student')

    def response(self, data=None, status=200):
        return Mock(status_code=status, json=Mock(return_value=data))

    @patch('apps.core.profile_photos.requests.request')
    def test_private_upload_checks_bucket_and_uses_opaque_filename(self, send):
        send.side_effect = [self.response({'public': False}), self.response({})]
        url = PhotoStorage().upload(self.user, b'image')
        self.assertRegex(url, r'/object/authenticated/student-photos/1/[a-f0-9]{32}\.webp$')
        self.assertNotIn('Authorization', send.call_args.kwargs['headers'])
        self.assertEqual(send.call_args.kwargs['headers']['apikey'], 'sb_secret_test')
        self.assertFalse(send.call_args.kwargs['allow_redirects'])

    @patch('apps.core.profile_photos.requests.request')
    def test_faculty_upload_uses_public_bucket(self, send):
        self.user.role = 'faculty'
        send.side_effect = [self.response({'public': True}), self.response({})]
        self.assertIn('/object/public/faculty-photos/1/', PhotoStorage().upload(self.user, b'image'))

    @patch('apps.core.profile_photos.requests.request')
    def test_refuses_public_student_bucket(self, send):
        send.return_value = self.response({'public': True})
        with self.assertRaises(PhotoStorageError):
            PhotoStorage().upload(self.user, b'image')
        self.assertEqual(send.call_count, 1)

    @patch('apps.core.profile_photos.requests.request')
    def test_signed_url_lasts_sixty_seconds(self, send):
        path = '1/' + 'a' * 32 + '.webp'
        self.user.uploaded_photo_url = STORAGE['SUPABASE_URL'] + '/storage/v1/object/authenticated/student-photos/' + path
        send.side_effect = [self.response({'public': False}), self.response({'signedURL': f'/object/sign/student-photos/{path}?token=example'})]
        self.assertIn('/storage/v1/object/sign/student-photos/', PhotoStorage().signed_student_url(self.user))
        self.assertEqual(send.call_args.kwargs['json'], {'expiresIn': 60})

    @patch('apps.core.profile_photos.requests.request')
    def test_does_not_delete_external_or_other_users_objects(self, send):
        storage = PhotoStorage()
        storage.delete(2, UPLOAD)
        storage.delete(1, 'https://elsewhere.example/photo.webp')
        storage.delete(1, UPLOAD.replace('a' * 32 + '.webp', '../other'))
        send.assert_not_called()

    @patch('apps.core.profile_photos.requests.request')
    def test_deletes_owned_object_only(self, send):
        send.return_value = self.response({})
        PhotoStorage().delete(1, UPLOAD)
        self.assertEqual(send.call_args.args[0], 'DELETE')
        self.assertEqual(send.call_args.kwargs['json'], {'prefixes': ['1/' + 'a' * 32 + '.webp']})

    @patch('apps.core.profile_photos.requests.request')
    def test_provider_error_does_not_expose_secrets(self, send):
        send.return_value = self.response({'secret': 'PRIVATE_BODY'}, status=403)
        with self.assertLogs('apps.core.profile_photos', level='WARNING') as logs:
            with self.assertRaises(PhotoStorageError) as exc:
                PhotoStorage().upload(self.user, b'image')
        self.assertNotIn('PRIVATE_BODY', str(exc.exception) + str(logs.output))
        self.assertNotIn('sb_secret_test', str(exc.exception) + str(logs.output))

    @override_settings(SUPABASE_SECRET_KEY='')
    def test_missing_config_has_clear_error(self):
        with self.assertRaisesRegex(PhotoStorageError, 'not configured'):
            PhotoStorage()


class PhotoDisplayTests(TestCase):
    def setUp(self):
        self.faculty = User.objects.create_user(username='picture-faculty', first_name='Picture', role='faculty', college='CCS', google_photo_url=GOOGLE)
        self.profile = FacultyProfile.objects.create(user=self.faculty, faculty_id='picture-faculty', college_id='CCS')
        self.student = User.objects.create_user(username='picture-student', role='student', college='CCS', google_photo_url=GOOGLE + '-student')

    def test_faculty_cards_and_directory_use_all_three_fallback_states(self):
        head = User.objects.create_user(username='picture-head', role='depthead', college='CCS')
        for uploaded, google, expected in [(UPLOAD, GOOGLE, UPLOAD), ('', GOOGLE, GOOGLE), ('', '', '')]:
            with self.subTest(expected=expected):
                self.faculty.uploaded_photo_url, self.faculty.google_photo_url = uploaded, google
                self.faculty.save()
                response = self.client.get(reverse('core:dashboard_public'))
                self.assertEqual(response.context['faculty_cards'][0]['photo_url'], expected)
                if expected:
                    self.assertContains(response, f'src="{expected}"')
                self.client.force_login(self.student)
                with patch('apps.students.views.refresh_faculty_status'):
                    response = self.client.get(reverse('students:api_faculty_statuses'))
                self.assertEqual(response.json()['faculty'][0]['photo_url'], expected)
                self.client.force_login(head)
                response = self.client.get(reverse('depthead:faculty_monitoring'))
                self.assertEqual(response.context['faculty_list'][0]['photo_url'], expected)
                response = self.client.get(reverse('depthead:faculty_monitoring_data'))
                self.assertEqual(response.json()['faculty_list'][0]['photo_url'], expected)
                self.client.logout()

    def test_student_profile_does_not_expose_permanent_private_storage_url(self):
        self.student.uploaded_photo_url = 'https://project.supabase.co/storage/v1/object/authenticated/student-photos/secret'
        self.student.save()
        self.client.force_login(self.student)
        response = self.client.get(reverse('students:profile'))
        self.assertContains(response, reverse('core:profile_photo_image', args=[self.student.pk]))
        self.assertNotContains(response, self.student.uploaded_photo_url)
        self.assertNotContains(response, 'src="' + GOOGLE + '-student"')

    def test_student_profile_google_and_initial_fallback(self):
        self.client.force_login(self.student)
        self.assertContains(self.client.get(reverse('students:profile')), f'src="{GOOGLE}-student"')
        self.student.google_photo_url = ''
        self.student.save()
        response = self.client.get(reverse('students:profile'))
        self.assertContains(response, 'fs-avatar-fallback">P</span>')

    def test_faculty_profile_and_manage_tables_show_faculty_photo(self):
        self.client.force_login(self.faculty)
        self.assertContains(self.client.get(reverse('faculty:profile')), f'src="{GOOGLE}"')
        for role, route in [('depthead', 'depthead:admin_faculty'), ('superadmin', 'superadmin:manage_faculty')]:
            admin = User.objects.create_user(username='photo-' + role, role=role, college='CCS')
            self.client.force_login(admin)
            self.assertContains(self.client.get(reverse(route)), f'src="{GOOGLE}"')

    def test_student_profile_rejects_faculty(self):
        self.client.force_login(self.faculty)
        self.assertEqual(self.client.get(reverse('students:profile')).status_code, 403)
