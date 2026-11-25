"""Load an explicit database target BEFORE Django settings; do not print credentials."""
import argparse
import os
from pathlib import Path
import sys

from dotenv import dotenv_values


def main():
    parser = argparse.ArgumentParser(description=__doc__, add_help=False)
    parser.add_argument('--database-target', required=True, choices=('production', 'rehearsal'))
    args, _ = parser.parse_known_args()
    root = Path(__file__).resolve().parents[1]
    filename = '.env' if args.database_target == 'production' else '.env.rehearsal'
    values = dotenv_values(root / filename, interpolate=False)
    keys = ('DB_HOST', 'DB_PORT', 'DB_NAME', 'DB_USER', 'DB_PASSWORD')
    if not all(values.get(k) for k in keys):
        parser.error(f'Missing database details in {filename}.')
    # An existing shell setting must not override the selected target.
    os.environ.update({k: values[k] for k in keys})
    os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings.development'
    os.environ['EMAIL_BACKEND'] = 'django.core.mail.backends.console.EmailBackend'
    sys.path.insert(0, str(root))
    from django.core.management import execute_from_command_line
    execute_from_command_line(['manage.py', 'prepare_faculty_test_requests', *sys.argv[1:]])


if __name__ == '__main__':
    main()
