"""Explicit bootstrap with preview; never promotes accounts during migrations."""
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.core.validators import validate_email
from django.db import transaction

from apps.core.models import School, User
from apps.core.school_scope import ALL_SCHOOLS, school_scope
from apps.systemadmin.services import require_replacement_superadmin


class Command(BaseCommand):
    help = 'Preview creation/conversion of a schoolless System Admin. Use explicit settings and --apply to save.'

    def add_arguments(self, parser):
        parser.add_argument('--email', required=True)
        parser.add_argument('--username')
        parser.add_argument('--convert-existing', action='store_true')
        parser.add_argument('--apply', action='store_true')

    def handle(self, *args, **options):
        email = options['email'].strip().lower()
        try:
            validate_email(email)
        except ValidationError as error:
            raise CommandError('Enter a valid Google account email.') from error
        with school_scope(ALL_SCHOOLS), transaction.atomic():
            matches = list(User.objects.filter(email__iexact=email))
            if len(matches) > 1:
                raise CommandError('More than one account has this email. Resolve the ambiguity before converting.')
            user = matches[0] if matches else None
            if user and user.role == 'systemadmin' and user.school_id is None:
                self.stdout.write('This account is already a schoolless System Admin. No changes made.')
                return
            if user:
                if not options['convert_existing']:
                    raise CommandError('Account exists. Preview again with --convert-existing to convert it.')
                if user.role != 'superadmin' or not user.school_id or not user.is_active or user.account_status != 'active':
                    raise CommandError('Only an active school-assigned Super Admin can be converted.')
                school = School.objects.select_for_update().get(pk=user.school_id)
                user = User.objects.select_for_update().get(pk=user.pk)
                if (user.role != 'superadmin' or user.school_id != school.pk
                        or not user.is_active or user.account_status != 'active'):
                    raise CommandError('The account assignment changed. Review it and preview again.')
                try:
                    require_replacement_superadmin(user)
                except ValidationError as error:
                    raise CommandError('; '.join(error.messages)) from error
                self.stdout.write(f'Convert {email} from {school.code} Super Admin to schoolless System Admin. Another active school Super Admin remains.')
            else:
                if options['convert_existing']:
                    raise CommandError('No account matches this email. No changes made.')
                # Keep creation explicit and preserve Google authentication only.
                username = options['username'] or email
                if len(username) > 150 or User.objects.filter(username=username).exists():
                    raise CommandError('Choose an available --username of at most 150 characters.')
                from apps.core.invitations import validate_invite_identity
                try:
                    validate_invite_identity(email)
                except ValidationError as error:
                    raise CommandError('; '.join(error.messages)) from error
                user = User(username=username, email=email)
                user.set_unusable_password()
                self.stdout.write(f'Create schoolless System Admin {email} for verified Google login.')
            if not options['apply']:
                self.stdout.write('Preview only. Add --apply with the intended --settings to save.')
                return
            user.role = 'systemadmin'
            user.school = None
            user.college = None
            user.title = None
            user.profile_completed = True
            user.is_active = True
            user.account_status = 'active'
            user.save()
            self.stdout.write(self.style.SUCCESS('System Admin saved. Existing Google identity and password were preserved; no Django superuser permissions were granted.'))
