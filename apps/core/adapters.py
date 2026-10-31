import logging
from uuid import uuid4

from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from allauth.core.exceptions import ImmediateHttpResponse
from allauth.socialaccount.providers.base import AuthError, ProviderException
from allauth.socialaccount.providers.oauth2.client import OAuth2Error
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect, render
from django.contrib import messages
from requests.exceptions import RequestException, Timeout
from .models import FacultyInvite, DeptHeadInvite, SuperAdminInvite, School, User
from .profile_photos import safe_photo_url
from django.db import transaction
from .school_scope import school_scope
from .student_registration import reject_registration, student_school

logger = logging.getLogger(__name__)


class FacSyncSocialAdapter(DefaultSocialAccountAdapter):

    def on_authentication_error(self, request, provider, error=None, exception=None, extra_context=None):
        # Preserve allauth's normal cancellation flow. Failed callbacks still
        # fail; no state check, token exchange or authentication is retried here.
        if error == AuthError.CANCELLED:
            return super().on_authentication_error(
                request, provider, error=error, exception=exception, extra_context=extra_context,
            )

        if extra_context is not None and 'state_id' in extra_context:
            category = 'oauth_state_unavailable'
        elif isinstance(exception, Timeout):
            category = 'provider_timeout'
        elif isinstance(exception, RequestException):
            category = 'provider_request_failed'
        elif isinstance(exception, OAuth2Error):
            category = 'provider_exchange_failed'
        elif isinstance(exception, ProviderException):
            category = 'provider_response_invalid'
        elif isinstance(exception, PermissionDenied):
            category = 'permission_denied'
        elif 'error' in request.GET:
            category = 'provider_returned_error'
        elif not request.GET.get('code'):
            category = 'callback_code_missing'
        else:
            category = 'authentication_failed'

        reference = uuid4().hex[:12]
        # Fixed categories/allowlisted provider and booleans only. Never log
        # exception text, traceback, callback URLs, state/code values or cookies.
        provider_name = 'google' if getattr(provider, 'id', None) == 'google' else 'other'
        authenticated = bool(getattr(getattr(request, 'user', None), 'is_authenticated', False))
        logger.warning(
            'social_login_failure reference=%s provider=%s category=%s authenticated=%s has_state=%s has_code=%s',
            reference, provider_name, category, authenticated,
            bool(request.GET.get('state')), bool(request.GET.get('code')),
        )
        response = render(request, 'socialaccount/authentication_error.html', {
            'failure_reference': reference,
        }, status=401)
        response['Cache-Control'] = 'private, no-store'
        response['Referrer-Policy'] = 'no-referrer'
        raise ImmediateHttpResponse(response)

    @staticmethod
    def _verified_google_email(sociallogin):
        data = sociallogin.account.extra_data
        email = str(data.get('email', '')).strip().lower()
        verified = data.get('email_verified') is True or data.get('verified_email') is True
        verified = verified or any(address.verified and address.email.lower() == email
                                   for address in getattr(sociallogin, 'email_addresses', []))
        return email if sociallogin.account.provider == 'google' and verified else None

    @staticmethod
    def _deny_invite(request):
        messages.error(request, 'This invitation is unavailable or its school is suspended. Please contact the System Admin.')
        raise ImmediateHttpResponse(redirect('core:login'))

    def _save_student(self, request, sociallogin, form):
        email = self._verified_google_email(sociallogin)
        with transaction.atomic():
            user = sociallogin.user
            school = student_school(request, email, expected_school_id=user.school_id, lock=True)
            if user.pk is not None or User._base_manager.filter(email__iexact=email).exists():
                reject_registration(request, 'An account already exists for this email. Please sign in instead.')
            user.email = email
            user.school = school
            user.role = 'student'
            user.account_status = 'active'
            user.is_active = True
            user.is_staff = False
            user.is_superuser = False
            user.profile_completed = False
            user.college = None
            user.title = None
            with school_scope(school):
                saved = super().save_user(request, sociallogin, form)
                # A signup form must not override the verified Google identity
                # or the school/role chosen by the server.
                if saved.email.lower() != email or saved.school_id != school.pk or saved.role != 'student':
                    reject_registration(request, 'Your registration details changed. Please start registration again.')
                return saved

    def save_user(self, request, sociallogin, form=None):
        # This hook also runs after student signup and both invite activation paths.
        if sociallogin.account.provider == 'google':
            sociallogin.user.google_photo_url = safe_photo_url(sociallogin.account.extra_data.get('picture'))
        invite = getattr(sociallogin, '_facsync_invite', None)
        if sociallogin.user.role == 'student' and invite is None:
            return self._save_student(request, sociallogin, form)
        if sociallogin.user.role == 'systemadmin':
            # Bootstrap creates the account through a management command; signup
            # must never manufacture this role from serialized/session data.
            self._deny_invite(request)
        if sociallogin.user.role == 'superadmin':
            email = self._verified_google_email(sociallogin)
            invite = SuperAdminInvite.objects.filter(email__iexact=email, used=False, is_active=True).first() if email else None
            if invite is None:
                self._deny_invite(request)
        if sociallogin.user.role != 'systemadmin' and sociallogin.user.school_id is None:
            messages.error(request, 'Your institution is not yet registered with FacSync')
            raise ImmediateHttpResponse(redirect('core:register'))
        with transaction.atomic():
            if invite is not None:
                # School lock serializes activation with suspension. The locked
                # invitation supplies the final assignment, including after a
                # delayed allauth signup form/session round trip.
                school = School.objects.select_for_update().get(pk=invite.school_id)
                invite = type(invite).objects.select_for_update().select_related('school').filter(pk=invite.pk, used=False).first()
                if invite is None:
                    self._deny_invite(request)
                if isinstance(invite, SuperAdminInvite):
                    email = self._verified_google_email(sociallogin)
                    if (not invite.is_active or invite.email.lower() != email or invite.school_id != school.pk
                            or User._base_manager.filter(email__iexact=email).exists()):
                        self._deny_invite(request)
                    sociallogin.user.school = school
                    sociallogin.user.role = 'superadmin'
                    sociallogin.user.account_status = 'active'
                    sociallogin.user.profile_completed = True
                    sociallogin.user.college = None
                    sociallogin.user.title = None
                if invite.school_id is None or not invite.school.is_active:
                    messages.error(request, 'Your school’s access to FacSync has been suspended. Please contact your school’s Super Admin.')
                    raise ImmediateHttpResponse(redirect('core:login'))
                with school_scope(invite.school):
                    saved = super().save_user(request, sociallogin, form)
                    if isinstance(invite, SuperAdminInvite):
                        if saved.email.lower() != invite.email.lower():
                            self._deny_invite(request)
                        # Consumption is a state-only write. Its inviter is a
                        # System Admin; school accounts cannot create these.
                        type(invite)._base_manager.filter(pk=invite.pk).update(used=True)
                    else:
                        invite.delete()
                    return saved
            return super().save_user(request, sociallogin, form)

    def pre_social_login(self, request, sociallogin):
        email = sociallogin.account.extra_data.get('email', '')
        user_exists = sociallogin.is_existing

        # A newly bootstrapped account has no SocialAccount yet. Connect only a
        # verified Google identity with the exact email and no previous Google
        # link. Converting an existing user preserves their original Google link.
        if not user_exists:
            verified = self._verified_google_email(sociallogin)
            bootstrap = list(User._base_manager.filter(email__iexact=email, role='systemadmin')) if email else []
            if (verified and len(bootstrap) == 1 and bootstrap[0].school_id is None
                    and bootstrap[0].is_active and bootstrap[0].account_status == 'active'
                    and not bootstrap[0].socialaccount_set.filter(provider='google').exists()):
                with transaction.atomic():
                    account = User._base_manager.select_for_update().get(pk=bootstrap[0].pk)
                    if (account.role != 'systemadmin' or account.school_id is not None
                            or not account.is_active or account.account_status != 'active'
                            or account.socialaccount_set.filter(provider='google').exists()):
                        self._deny_invite(request)
                    sociallogin.connect(request, account)
                user_exists = True
            elif bootstrap:
                self._deny_invite(request)

        if user_exists:
            existing_user = sociallogin.user
            if existing_user.account_status == 'pending':
                messages.error(request, "Your registration is pending review. Please contact your College Head.", extra_tags='registration_status')
                raise ImmediateHttpResponse(redirect('core:login'))
            elif existing_user.account_status == 'declined':
                messages.error(request, "Your registration was declined. Please contact your College Head.", extra_tags='registration_status')
                raise ImmediateHttpResponse(redirect('core:login'))
            elif existing_user.account_status == 'deactivated':
                messages.error(request, "Your account has been deactivated. Please contact a Super Admin.")
                raise ImmediateHttpResponse(redirect('core:login'))
            if existing_user.role != 'systemadmin' and (
                existing_user.school_id is None or not existing_user.school.is_active
            ):
                message = ('Your school’s access to FacSync has been suspended. Please contact your school’s Super Admin.'
                           if existing_user.school_id else 'Your account is not assigned to a school. Please contact your administrator.')
                messages.error(request, message)
                raise ImmediateHttpResponse(redirect('core:login'))
            if sociallogin.account.provider == 'google':
                existing_user.google_photo_url = safe_photo_url(sociallogin.account.extra_data.get('picture'))
                existing_user.save(update_fields=['google_photo_url'])
            return

        #new account, check for faculty invites first
        superadmin_invite = SuperAdminInvite.objects.select_related('school').filter(email__iexact=email).first()
        if superadmin_invite is not None:
            if (not self._verified_google_email(sociallogin) or superadmin_invite.used
                    or not superadmin_invite.is_active or not superadmin_invite.school.is_active):
                self._deny_invite(request)
            sociallogin.user.role = 'superadmin'
            sociallogin.user.account_status = 'active'
            sociallogin.user.school = superadmin_invite.school
            sociallogin.user.profile_completed = True
            sociallogin.user.college = None
            sociallogin.user.title = None
            sociallogin._facsync_invite = superadmin_invite
            request.session.pop('registration_role', None)
            return

        try:
            invite = FacultyInvite.objects.select_related('school').get(email__iexact=email, used=False)
            if invite.school_id is None or not invite.school.is_active:
                messages.error(request, 'Your school’s access to FacSync has been suspended. Please contact your school’s Super Admin.')
                raise ImmediateHttpResponse(redirect('core:login'))
            sociallogin.user.role = 'faculty'
            sociallogin.user.account_status = 'active'
            sociallogin.user.college = invite.college
            sociallogin.user.school = invite.school
            sociallogin._facsync_invite = invite
            if 'registration_role' in request.session:
                del request.session['registration_role']
            return
        except FacultyInvite.DoesNotExist:
            pass

        #new account, no faculty invite, check for depthead invites
        try:
            depthead_invite = DeptHeadInvite.objects.select_related('school').get(email__iexact=email, used=False)
            if depthead_invite.school_id is None or not depthead_invite.school.is_active:
                messages.error(request, 'Your school’s access to FacSync has been suspended. Please contact your school’s Super Admin.')
                raise ImmediateHttpResponse(redirect('core:login'))
            sociallogin.user.role = 'depthead'
            sociallogin.user.account_status = 'active'
            sociallogin.user.college = depthead_invite.college
            sociallogin.user.title = depthead_invite.title
            sociallogin.user.school = depthead_invite.school
            sociallogin._facsync_invite = depthead_invite
            if 'registration_role' in request.session:
                del request.session['registration_role']
            return
        except DeptHeadInvite.DoesNotExist:
            pass
        
        #No invite matched — fall back to session-role-based registration flow
        role = request.session.get('registration_role')

        if role == 'faculty':
            for key in ('registration_role', 'pending_faculty_email', 'pending_faculty_name', 'pending_faculty_uid'):
                request.session.pop(key, None)
            messages.error(request, "Faculty self-registration is no longer available. If you were invited by a College Head or Super Admin, please check your email for an activation link, or contact them for an invite.")
            raise ImmediateHttpResponse(redirect('core:register'))

        if role != 'student':
            messages.error(request, "No account found. Please register first.")
            raise ImmediateHttpResponse(redirect('core:register'))

        if role == 'student':
            school = student_school(request, self._verified_google_email(sociallogin))
            sociallogin.user.role = 'student'
            sociallogin.user.account_status = 'active'
            sociallogin.user.school = school
            sociallogin.user.profile_completed = False
            sociallogin.user.college = None
            sociallogin.user.title = None

        if 'registration_role' in request.session:
            del request.session['registration_role']
