from functools import wraps
from django.core.exceptions import PermissionDenied
from .school_scope import ALL_SCHOOLS, require_school, school_scope

def role_required(role):
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            user = request.user
            if not user.is_authenticated or user.role != role or not user.is_active or user.account_status != 'active':
                raise PermissionDenied
            if role == 'systemadmin':
                if user.school_id is not None:
                    raise PermissionDenied
                scope = ALL_SCHOOLS
            else:
                scope = require_school(user.school)
            with school_scope(scope):
                return view_func(request, *args, **kwargs)
        return wrapper
    return decorator
