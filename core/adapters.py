from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from allauth.core.exceptions import ImmediateHttpResponse
from django.shortcuts import redirect
from django.contrib import messages
from .models import FacultyInvite

class FacSyncSocialAdapter(DefaultSocialAccountAdapter):

    def pre_social_login(self, request, sociallogin):
        email = sociallogin.account.extra_data.get('email', '')
        user_exists = sociallogin.is_existing

        #If the account already exists,normal login proceed
        if user_exists:
            return

        #New account 
        role = request.session.get('registration_role')

        if not role:
            #No role in session, they login without registering 
            messages.error(request, "No account found. Please register first.")
            raise ImmediateHttpResponse(redirect('core:register'))

        if role == 'student':
            sociallogin.user.role = 'student'
            sociallogin.user.account_status = 'active'
            #sociallogin.user gets saved automatically by allauth 

        elif role == 'faculty':
            try:
                invite = FacultyInvite.objects.get(email__iexact=email, used=False)
                sociallogin.user.role = 'faculty'
                sociallogin.user.account_status = 'active'
                sociallogin.user.department = invite.department
                invite.used = True
                invite.save()
            except FacultyInvite.DoesNotExist:
                #Not pre-added: redirect to the self-registration
                request.session['pending_faculty_email'] = email
                request.session['pending_faculty_name'] = sociallogin.account.extra_data.get('name', '')
                raise ImmediateHttpResponse(redirect('core:faculty_pending_registration'))

        #clear session flag after used
        if 'registration_role' in request.session:
            del request.session['registration_role']