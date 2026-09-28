"""Django email transport using Brevo's transactional HTTPS API."""

import logging
from dataclasses import dataclass
from email.utils import parseaddr

import requests
from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend


logger = logging.getLogger(__name__)


class BrevoEmailError(Exception):
    """A sanitized transport or message validation failure."""


@dataclass(frozen=True)
class BatchSendResult:
    accepted: int = 0
    rejected: int = 0
    unknown: int = 0


class BrevoEmailBackend(BaseEmailBackend):
    endpoint = 'https://api.brevo.com/v3/smtp/email'
    timeout = (5, 20)  # Connection and read timeouts, in seconds.

    def __init__(self, fail_silently=False, **kwargs):
        super().__init__(**kwargs)
        self.fail_silently = fail_silently

    @staticmethod
    def _address(value):
        if not isinstance(value, str) or '\r' in value or '\n' in value:
            raise BrevoEmailError('Invalid email address.')
        try:
            name, address = parseaddr(value)
        except ValueError:
            raise BrevoEmailError('Invalid email address.') from None
        if not address or '@' not in address:
            raise BrevoEmailError('Invalid email address.')
        return {'email': address, **({'name': name} if name else {})}

    def _payload(self, message):
        # Validate Django headers before bypassing its MIME serialization.
        message.message()
        if message.attachments or message.extra_headers:
            raise BrevoEmailError('Attachments and custom headers are not supported.')
        if len(message.reply_to) > 1:
            raise BrevoEmailError('Only one reply-to address is supported.')
        if message.content_subtype not in ('plain', 'html'):
            raise BrevoEmailError('Unsupported email body type.')
        payload = {
            'sender': self._address(message.from_email),
            'subject': str(message.subject),
            'htmlContent' if message.content_subtype == 'html' else 'textContent': message.body,
        }
        for field in ('to', 'cc', 'bcc'):
            addresses = getattr(message, field)
            if addresses:
                payload[field] = [self._address(address) for address in addresses]
        if message.reply_to:
            payload['replyTo'] = self._address(message.reply_to[0])
        for content, mimetype in getattr(message, 'alternatives', ()):
            if mimetype != 'text/html' or 'htmlContent' in payload:
                raise BrevoEmailError('Unsupported or duplicate email alternative.')
            payload['htmlContent'] = content
        return payload

    def _send(self, message):
        api_key = getattr(settings, 'BREVO_API_KEY', '').strip()
        if not api_key:
            raise BrevoEmailError('BREVO_API_KEY is required for the Brevo backend.')
        try:
            payload = self._payload(message)
        except BrevoEmailError:
            raise
        except (ValueError, TypeError):
            raise BrevoEmailError('Invalid email message.') from None
        try:
            # No retries: an ambiguous timeout may occur after provider acceptance.
            with requests.post(
                self.endpoint,
                headers={'api-key': api_key, 'Accept': 'application/json'},
                json=payload,
                timeout=self.timeout,
                allow_redirects=False,
            ) as response:
                if response.status_code != 201:
                    raise BrevoEmailError(
                        f'Brevo rejected the email (HTTP {response.status_code}).'
                    )
                try:
                    result = response.json()
                except ValueError:
                    raise BrevoEmailError('Invalid Brevo acceptance response.') from None
                if not isinstance(result, dict) or not result.get('messageId'):
                    raise BrevoEmailError('Brevo response omitted the message ID.')
        except requests.RequestException:
            # Do not expose request headers, response bodies, or credentials.
            raise BrevoEmailError('Brevo HTTPS connection failed or timed out.') from None

    def send_messages(self, email_messages):
        accepted = 0
        for message in email_messages or ():
            if not message.recipients():
                continue
            try:
                self._send(message)
            except BrevoEmailError as exc:
                logger.error('Brevo email failed: %s', exc)
                if not self.fail_silently:
                    raise
            else:
                accepted += 1
        return accepted

    def send_personalized_batch(self, email_messages):
        """Submit private, single-recipient versions; never retry ambiguous sends.

        Unlike send_messages(), this returns submission outcomes per chunk.
        Validation completes before any network calls. A provider rejection
        affects a whole chunk; a timeout or malformed success is unknown.
        """
        messages = list(email_messages or ())
        if not messages:
            return BatchSendResult()
        api_key = getattr(settings, 'BREVO_API_KEY', '').strip()
        if not api_key:
            raise BrevoEmailError('BREVO_API_KEY is required for the Brevo backend.')
        batch_size = getattr(settings, 'BREVO_BATCH_SIZE', 100)
        if isinstance(batch_size, bool) or not isinstance(batch_size, int) or not 1 <= batch_size <= 1000:
            raise BrevoEmailError('BREVO_BATCH_SIZE must be between 1 and 1000.')
        payloads = []
        for message in messages:
            if len(message.to) != 1 or message.cc or message.bcc:
                raise BrevoEmailError('Batch messages require one To recipient and no CC or BCC.')
            try:
                payload = self._payload(message)
            except BrevoEmailError:
                raise
            except (ValueError, TypeError):
                raise BrevoEmailError('Invalid email message.') from None
            if payloads and payload['sender'] != payloads[0]['sender']:
                raise BrevoEmailError('Batch messages must have the same sender.')
            payloads.append(payload)

        accepted = rejected = unknown = 0
        with requests.Session() as session:
            for offset in range(0, len(payloads), batch_size):
                chunk = payloads[offset:offset + batch_size]
                first = chunk[0]
                body = {
                    'sender': first['sender'],
                    'subject': first['subject'],
                    'messageVersions': [
                        {key: value for key, value in payload.items() if key != 'sender'}
                        for payload in chunk
                    ],
                }
                # Brevo requires global content to allow per-version overrides.
                for field in ('htmlContent', 'textContent'):
                    if field in first:
                        body[field] = first[field]
                try:
                    with session.post(
                        self.endpoint, headers={'api-key': api_key, 'Accept': 'application/json'},
                        json=body, timeout=self.timeout, allow_redirects=False,
                    ) as response:
                        if response.status_code == 201:
                            try:
                                result = response.json()
                            except ValueError:
                                result = None
                            ids = result.get('messageIds') if isinstance(result, dict) else None
                            if (isinstance(ids, list) and len(ids) == len(chunk)
                                    and all(isinstance(value, str) and value for value in ids)):
                                accepted += len(chunk)
                            else:
                                unknown += len(chunk)
                                logger.error('Brevo batch acceptance response was incomplete; not retrying.')
                        elif 400 <= response.status_code < 500 and response.status_code != 408:
                            rejected += len(chunk)
                            logger.error('Brevo batch rejected (HTTP %s).', response.status_code)
                        else:
                            unknown += len(chunk)
                            logger.error('Brevo batch outcome unknown (HTTP %s); not retrying.', response.status_code)
                except requests.RequestException:
                    unknown += len(chunk)
                    logger.error('Brevo batch connection failed or timed out; not retrying.')
        return BatchSendResult(accepted, rejected, unknown)
