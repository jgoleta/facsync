from django.core.management.base import BaseCommand

from faculty.services.google_calendar import (
    GoogleCalendarError,
    sync_google_calendar,
)
from faculty.models import FacultyProfile, GoogleCalendarConnection


class Command(BaseCommand):
    help = 'Poll enabled faculty Google Calendars and reconcile local schedule data.'

    def handle(self, *args, **options):
        """Poll every enabled faculty calendar and report successful/failed syncs."""
        connections = GoogleCalendarConnection.objects.filter(
            user__faculty_profile__sync_enabled=True,
        ).select_related('user')
        success = 0
        failures = 0
        for connection in connections:
            try:
                sync_google_calendar(connection.user)
                success += 1
            except (GoogleCalendarError, FacultyProfile.DoesNotExist) as exc:
                failures += 1
                self.stderr.write(self.style.WARNING(
                    f'{connection.user}: calendar sync failed: {exc}'
                ))
        self.stdout.write(f'Synced {success} calendar(s); {failures} failed.')
