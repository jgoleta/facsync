"""Validated avatar uploads and server-only Supabase Storage access."""
import logging
import re
import uuid
import warnings
from io import BytesIO
from pathlib import PurePath
from urllib.parse import urlsplit

import requests
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import URLValidator

logger = logging.getLogger(__name__)
MAX_PHOTO_BYTES = 2 * 1024 * 1024
MAX_PHOTO_PIXELS = 16_000_000
FORMATS = {'jpg': 'JPEG', 'jpeg': 'JPEG', 'png': 'PNG', 'webp': 'WEBP'}
MIMES = {'JPEG': 'image/jpeg', 'PNG': 'image/png', 'WEBP': 'image/webp'}


class PhotoStorageError(Exception):
    pass


def safe_photo_url(value):
    if not isinstance(value, str) or len(value) > 2048:
        return ''
    try:
        URLValidator(schemes=['https'])(value)
        if urlsplit(value).username or urlsplit(value).password:
            return ''
    except (ValidationError, ValueError):
        return ''
    return value


def normalize_photo(upload):
    """Decode and re-encode pixels so extensions/MIME alone cannot validate a file."""
    from PIL import Image, ImageOps, UnidentifiedImageError
    if not upload or upload.size > MAX_PHOTO_BYTES:
        raise ValidationError('Choose an image no larger than 2 MB.')
    expected = FORMATS.get(PurePath(upload.name).suffix.lower().lstrip('.'))
    if not expected or upload.content_type != MIMES[expected]:
        raise ValidationError('Choose a JPG, PNG or WebP image.')
    raw = upload.read(MAX_PHOTO_BYTES + 1)
    if len(raw) > MAX_PHOTO_BYTES:
        raise ValidationError('Choose an image no larger than 2 MB.')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(BytesIO(raw)) as original:
                if original.format != expected:
                    raise ValidationError('The image contents do not match its file type.')
                if original.width * original.height > MAX_PHOTO_PIXELS:
                    raise ValidationError('Choose an image with no more than 16 megapixels.')
                if getattr(original, 'n_frames', 1) != 1:
                    raise ValidationError('Choose a still image, not an animated image.')
                original.verify()
            with Image.open(BytesIO(raw)) as original:
                oriented = ImageOps.exif_transpose(original)
                oriented.thumbnail((512, 512))
                pixels = oriented.convert('RGBA')
                # Create a new image containing pixels only (no EXIF, text or ICC metadata).
                clean = Image.new('RGBA', pixels.size)
                clean.paste(pixels)
                output = BytesIO()
                clean.save(output, format='WEBP', quality=85)
                return output.getvalue()
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError,
            Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise ValidationError('This image is damaged or cannot be processed.') from exc


class PhotoStorage:
    def __init__(self):
        self.base = settings.SUPABASE_URL.rstrip('/')
        key = settings.SUPABASE_SECRET_KEY
        if not safe_photo_url(self.base) or not key:
            raise PhotoStorageError('Photo uploads are not configured yet. Your Google photo still works.')
        self.headers = {'apikey': key}
        # Modern secret keys use apikey; the legacy service_role JWT also uses Bearer auth.
        if not key.startswith('sb_secret_'):
            self.headers['Authorization'] = f'Bearer {key}'

    def request(self, method, path, **kwargs):
        headers = {**self.headers, **kwargs.pop('headers', {})}
        try:
            response = requests.request(method, f'{self.base}/storage/v1/{path}',
                                        headers=headers, timeout=(5, 15), allow_redirects=False, **kwargs)
        except requests.RequestException:
            logger.warning('profile_photo_storage outcome=network_error')
            raise PhotoStorageError('Photo storage is unavailable. Please try again.') from None
        if not 200 <= response.status_code < 300:
            logger.warning('profile_photo_storage http_status=%s', response.status_code)
            raise PhotoStorageError('Photo storage is unavailable. Please try again.')
        return response

    def bucket(self, role):
        bucket = (settings.SUPABASE_STUDENT_PHOTO_BUCKET if role == 'student'
                  else settings.SUPABASE_FACULTY_PHOTO_BUCKET)
        if not re.fullmatch(r'[A-Za-z0-9_-]+', bucket):
            raise PhotoStorageError('The photo storage bucket is not configured correctly.')
        return bucket

    def check_visibility(self, bucket, *, public):
        try:
            details = self.request('GET', f'bucket/{bucket}').json()
        except ValueError:
            raise PhotoStorageError('Photo storage returned an invalid response.') from None
        if not isinstance(details, dict) or details.get('public') is not public:
            raise PhotoStorageError('The photo storage privacy settings need administrator attention.')

    def upload(self, user, content):
        bucket = self.bucket(user.role)
        public = user.role == 'faculty'
        self.check_visibility(bucket, public=public)
        path = f'{user.pk}/{uuid.uuid4().hex}.webp'
        self.request('POST', f'object/{bucket}/{path}', data=content,
                     headers={'Content-Type': 'image/webp', 'x-upsert': 'false', 'Cache-Control': 'max-age=3600' if public else 'max-age=0'})
        access = 'public' if public else 'authenticated'
        return f'{self.base}/storage/v1/object/{access}/{bucket}/{path}'

    def owned_object(self, user_id, url):
        # Only delete/sign generated objects in our project belonging to this user.
        for role, access in [('faculty', 'public'), ('student', 'authenticated')]:
            bucket = self.bucket(role)
            prefix = f'{self.base}/storage/v1/object/{access}/{bucket}/{user_id}/'
            if url.startswith(prefix) and re.fullmatch(r'[0-9a-f]{32}\.webp', url[len(prefix):]):
                return bucket, f'{user_id}/{url[len(prefix):]}', role
        return None

    def signed_student_url(self, user):
        owned = self.owned_object(user.pk, user.uploaded_photo_url)
        if not owned or owned[2] != 'student':
            raise PhotoStorageError('This private photo is unavailable.')
        bucket, path, _ = owned
        self.check_visibility(bucket, public=False)
        try:
            data = self.request('POST', f'object/sign/{bucket}/{path}', json={'expiresIn': 60}).json()
            relative = data['signedURL']
            if not isinstance(relative, str) or not relative.startswith(f'/object/sign/{bucket}/{path}?'):
                raise ValueError
        except (ValueError, KeyError, TypeError):
            raise PhotoStorageError('Photo storage returned an invalid response.') from None
        return f'{self.base}/storage/v1{relative}'

    def delete(self, user_id, url):
        owned = self.owned_object(user_id, url)
        if owned:
            bucket, path, _ = owned
            self.request('DELETE', f'object/{bucket}', json={'prefixes': [path]})


def delete_photo_safely(user_id, url):
    if not url:
        return
    try:
        PhotoStorage().delete(user_id, url)
    except PhotoStorageError:
        # No keys, URLs, provider bodies or personally identifying details in logs.
        logger.warning('profile_photo_cleanup outcome=failed; storage cleanup may be needed')
