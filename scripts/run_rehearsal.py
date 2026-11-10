"""Start localhost against a separate rehearsal DB and storage, with console emails."""
import os
from pathlib import Path
import re
import runpy
import sys
from urllib.parse import urlparse

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]


def project_reference(values):
    host = values.get('DB_HOST', '').strip().lower()
    direct = re.fullmatch(r'db\.([a-z0-9]+)\.supabase\.co', host)
    if direct:
        return direct.group(1)
    pooled = re.fullmatch(r'postgres\.([a-z0-9]+)', values.get('DB_USER', '').strip().lower())
    return pooled.group(1) if pooled and host.endswith('.pooler.supabase.com') else None


def validate_target(rehearsal, production):
    if not all(rehearsal.get(key) for key in ('DB_HOST', 'DB_PORT', 'DB_NAME', 'DB_USER', 'DB_PASSWORD')):
        raise ValueError('Fill all five DB fields in .env.rehearsal before starting.')
    target, live = project_reference(rehearsal), project_reference(production)
    if not target or not live or target == live:
        raise ValueError('Cannot confirm a separate rehearsal project. Nothing was started.')
    if urlparse(production.get('SUPABASE_URL', '')).hostname == f'{target}.supabase.co':
        raise ValueError('Rehearsal matches production storage. Nothing was started.')
    storage = rehearsal.get('SUPABASE_URL', '')
    if storage and (urlparse(storage).scheme != 'https' or urlparse(storage).hostname != f'{target}.supabase.co'):
        raise ValueError('Rehearsal storage URL must belong to the rehearsal database project.')


def configure(rehearsal, production):
    validate_target(rehearsal, production)
    os.environ.update({key: rehearsal[key] for key in ('DB_HOST', 'DB_PORT', 'DB_NAME', 'DB_USER', 'DB_PASSWORD')})
    # Empty overrides deliberately prevent falling back to production storage or scheduler keys.
    for key in ('SUPABASE_URL', 'SUPABASE_SECRET_KEY', 'SCHOOL_EVIDENCE_CLEANUP_SECRET'):
        os.environ[key] = rehearsal.get(key, '') or ''
    for key, default in [('SUPABASE_FACULTY_PHOTO_BUCKET', 'faculty-photos'),
            ('SUPABASE_STUDENT_PHOTO_BUCKET', 'student-photos'), ('SUPABASE_SCHOOL_EVIDENCE_BUCKET', 'school-verification')]:
        os.environ[key] = rehearsal.get(key) or default
    os.environ.update(DJANGO_SETTINGS_MODULE='config.settings.development',
        EMAIL_BACKEND='django.core.mail.backends.console.EmailBackend', SITE_URL='http://127.0.0.1:8000',
        CONSULTATION_EMAILS_ENABLED='False', AUTOMATIC_STATUS_EMAIL_QUEUE_ENABLED='False',
        STATUS_SCHEDULER_SECRET='', GEMINI_API_KEY='')


def main():
    if sys.argv[1:] not in ([], ['--check']):
        raise ValueError('Use without arguments to start localhost, or --check for Django checks.')
    configure(dotenv_values(ROOT/'.env.rehearsal', interpolate=False), dotenv_values(ROOT/'.env', interpolate=False))
    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT))
    print('Using separate rehearsal database and storage. Emails print in this terminal; no email is delivered.')
    sys.argv = ['manage.py', 'check' if '--check' in sys.argv else 'runserver', '--settings=config.settings.development']
    runpy.run_path(str(ROOT/'manage.py'), run_name='__main__')


if __name__ == '__main__':
    try:
        main()
    except ValueError as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1)
