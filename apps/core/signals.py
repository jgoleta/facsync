from allauth.core.exceptions import ImmediateHttpResponse
from django.shortcuts import redirect
from django.contrib import messages

ALLOWED_DOMAIN = "gbox.adnu.edu.ph"  


def cleanup_user_photo(sender, instance, using, **kwargs):
    from django.db import transaction
    from .profile_photos import delete_photo_safely
    if instance.uploaded_photo_url:
        user_id, photo_url = instance.pk, instance.uploaded_photo_url
        transaction.on_commit(lambda: delete_photo_safely(user_id, photo_url), using=using)

def google_login_domain_check(sender, request, sociallogin, **kwargs):
    email = sociallogin.account.extra_data.get('email', '')

    # TEMP: domain restriction disabled for multi-role testing with personal accounts
    # if not email.endswith(f"@{ALLOWED_DOMAIN}"):
    #     messages.error(request, "Please sign in using your official ADNU Google account.")
    #     raise ImmediateHttpResponse(redirect('core:login'))
