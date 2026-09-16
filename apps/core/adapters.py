import email
from urllib import request

from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from allauth.core.exceptions import ImmediateHttpResponse
from django.shortcuts import redirect
from django.contrib import messages
from .models import FacultyInvite, DeptHeadInvite

class FacSyncSocialAdapter(DefaultSocialAccountAdapter):

    def pre_social_login(self, request, sociallogin):
        email = sociallogin.account.extra_data.get('email', '')
        user_exists = sociallogin.is_existing

        if user_exists:
            existing_user = sociallogin.user
            if existing_user.account_status == 'pending':
                messages.error(request, "Your registration is pending review. Please contact your College Head.")
                raise ImmediateHttpResponse(redirect('core:login'))
            elif existing_user.account_status == 'declined':
                messages.error(request, "Your registration was declined. Please contact your College Head.")
                raise ImmediateHttpResponse(redirect('core:login'))
            elif existing_user.account_status == 'deactivated':
                messages.error(request, "Your account has been deactivated. Please contact a Super Admin.")
                raise ImmediateHttpResponse(redirect('core:login'))
            return

        #new account, check for faculty invites first
        try:
            invite = FacultyInvite.objects.get(email__iexact=email, used=False)
            sociallogin.user.role = 'faculty'
            sociallogin.user.account_status = 'active'
            sociallogin.user.college = invite.college
            invite.used = True
            invite.delete()
            if 'registration_role' in request.session:
                del request.session['registration_role']
            return
        except FacultyInvite.DoesNotExist:
            pass

        #new account, no faculty invite, check for depthead invites
        try:
            depthead_invite = DeptHeadInvite.objects.get(email__iexact=email, used=False)
            sociallogin.user.role = 'depthead'
            sociallogin.user.account_status = 'active'
            sociallogin.user.college = depthead_invite.college
            sociallogin.user.title = depthead_invite.title
            depthead_invite.used = True
            depthead_invite.delete()
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
            sociallogin.user.role = 'student'
            sociallogin.user.account_status = 'active'

        if 'registration_role' in request.session:
            del request.session['registration_role']
