"""Private queue subscriber, not a public website endpoint."""
import logging
import os

from vercel.queue import Message, subscribe

logger = logging.getLogger(__name__)


@subscribe(topic='facsync-consultation-emails', consumer_group='consultation-emails', max_attempts=1)
def deliver_consultation_email(message: Message[dict[str, object]]):
    # Publishing is deduplicated by request/event. Do not resend when an ACK is
    # lost: without a delivery ledger/provider idempotency, retrying may duplicate mail.
    if message.metadata.delivery_count > 1:
        logger.warning('consultation_email_redelivery_skipped')
        return
    import django
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.production')
    django.setup()
    from django.db import close_old_connections
    from .consultation_emails import send_consultation_email
    close_old_connections()
    try:
        send_consultation_email(message.payload)
    finally:
        close_old_connections()
