from django.core.management.base import BaseCommand
from apps.core.school_evidence_cleanup import cleanup_school_evidence


class Command(BaseCommand):
    help = 'Preview school evidence older than 90 days after a final decision; use --apply to delete files.'

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true')

    def handle(self, *args, **options):
        self.stdout.write(str(cleanup_school_evidence(apply=options['apply'])))
