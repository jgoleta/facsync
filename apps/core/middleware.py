from django.http import HttpResponseForbidden, JsonResponse

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
                message = 'Your school’s access to FacSync has been suspended. Please contact your school’s Super Admin.'
            elif request.path.startswith('/admin/') and not system_admin:
                message = 'Only a System Admin can access database administration.'
            if message and request.path not in {'/accounts/logout/', '/login/'}:
                if '/api/' in request.path or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({'error': message}, status=403)
                return HttpResponseForbidden(message)
            request.school = None if system_admin else user.school if user.school_id else None
            with school_scope(ALL_SCHOOLS if system_admin else request.school):
                response = self.get_response(request)
                response['Cache-Control'] = 'private, no-store'
                return response
