from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import redirect, render

from .school_scope import ALL_SCHOOLS, school_scope


class SchoolScopeMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Resolve the login identity outside any inherited tenant context.
        with school_scope(None):
            user = request.user
            if not user.is_authenticated:
                return self.get_response(request)
            system_admin = user.role == 'systemadmin' and user.school_id is None
            message = None
            if not user.is_active or user.account_status != 'active':
                message = 'Your account is not active. Please contact your administrator.'
            elif not system_admin and user.school_id is None:
                message = 'Your account is not assigned to a school. Please contact your administrator.'
            elif not system_admin and not user.school.is_active:
                message = 'Your school’s access to FacSync has been suspended. Please contact your school’s School Admin.'
            elif request.path.startswith('/admin/') and not system_admin:
                message = 'Only authorized FacSync Super Admin accounts can access database administration.'
            if message and request.path not in {'/accounts/logout/', '/login/'}:
                if '/api/' in request.path or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({'error': message}, status=403)
                return HttpResponseForbidden(message)
            request.school = None if system_admin else user.school if user.school_id else None
            with school_scope(ALL_SCHOOLS if system_admin else request.school):
                from .role_access import available_roles
                roles = available_roles(user)
                enabled = {role for role, _ in roles}
                public_auth = request.path in {'/accounts/logout/', '/login/'}
                json_request = '/api/' in request.path or request.headers.get('X-Requested-With') == 'XMLHttpRequest'
                if not roles and not public_auth:
                    response = (JsonResponse({'error': 'No enabled role is available for this account.'}, status=403)
                                if json_request else render(request, 'core/roleAccessUnavailable.html', status=403))
                elif (request.session.get('active_role') and request.session['active_role'] not in enabled
                      and not public_auth):
                    request.session.pop('active_role', None)
                    if json_request:
                        response = JsonResponse({'error': 'Your selected role is no longer available. Choose another enabled role.'}, status=403)
                    else:
                        response = redirect('core:select_role' if len(roles) > 1 else 'core:post_login_redirect')
                else:
                    response = self.get_response(request)
                response['Cache-Control'] = 'private, no-store'
                return response
