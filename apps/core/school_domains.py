"""Exact school-domain eligibility, independent of invitations and email delivery.

The public-suffix snapshot ships with the pinned dependency. No DNS/HTTP requests
or writable cache are used. The denylist is a supporting check, not proof that a
domain belongs to a school; school requests still require manual review.
"""
import re

import tldextract
from django.core.exceptions import ValidationError
from django.core.validators import validate_email

PERSONAL_EMAIL_MESSAGE = 'Please use your school email address. Personal email addresses cannot be used for student or school registration.'
INVALID_DOMAIN_MESSAGE = 'Enter a valid school-owned email domain, without @, a URL, an IP address or a wildcard.'

# Extend this explicit list as providers are identified. Do not block by MX host:
# schools may legitimately use Google/Microsoft to host their own email domains.
PERSONAL_EMAIL_DOMAINS = frozenset('''
gmail.com googlemail.com yahoo.com yahoo.com.ph yahoo.co.uk yahoo.ca yahoo.com.au
yahoo.co.in yahoo.in yahoo.fr yahoo.de ymail.com rocketmail.com outlook.com
hotmail.com hotmail.co.uk hotmail.fr hotmail.de live.com live.co.uk live.com.ph
msn.com icloud.com me.com mac.com aol.com aim.com proton.me protonmail.com pm.me
mail.com email.com gmx.com gmx.net gmx.de zoho.com yandex.com yandex.ru
tutanota.com tuta.com tutamail.com fastmail.com mail.ru inbox.ru bk.ru list.ru
mailinator.com guerrillamail.com 10minutemail.com temp-mail.org disroot.org riseup.net
'''.split())
_extract = tldextract.TLDExtract(suffix_list_urls=(), cache_dir=None, include_psl_private_domains=True)
_hostname = re.compile(r'(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z](?:[a-z0-9-]{0,61}[a-z0-9])?')


def validate_school_owned_domain(value):
    if (not isinstance(value, str) or len(value) > 253 or not _hostname.fullmatch(value)):
        raise ValidationError(INVALID_DOMAIN_MESSAGE)
    if any(value == blocked or value.endswith('.' + blocked) for blocked in PERSONAL_EMAIL_DOMAINS):
        raise ValidationError(PERSONAL_EMAIL_MESSAGE)
    parsed = _extract(value)
    if not parsed.domain or not parsed.suffix:
        raise ValidationError(INVALID_DOMAIN_MESSAGE)


def school_domain_from_email(email):
    email = str(email or '').strip().lower()
    validate_email(email)
    domain = email.rsplit('@', 1)[1]
    validate_school_owned_domain(domain)
    return domain
