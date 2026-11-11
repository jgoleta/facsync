from functools import wraps
from django.core.exceptions import PermissionDenied
from .school_scope import ALL_SCHOOLS, require_school, school_scope

def role_required(role):
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            user = request.user
            allowed_roles = {role}
            if role in {'depthead', 'faculty'}:
                allowed_roles.add('officeadmin')
            if not user.is_authenticated or user.role not in allowed_roles or not user.is_active or user.account_status != 'active':
                raise PermissionDenied
            if role == 'systemadmin':
                if user.school_id is not None:
                    raise PermissionDenied
                scope = ALL_SCHOOLS
            else:
                scope = require_school(user.school)
            with school_scope(scope):
                if role == 'superadmin':
                    from .school_admin_access import has_school_admin_permission, VIEW_FEATURES
                    feature = VIEW_FEATURES.get(view_func.__name__, 'school_admins')
                    if not has_school_admin_permission(user, feature):
                        raise PermissionDenied('Your School Admin account does not have access to this feature.')
                if role == 'depthead':
                    from apps.depthead.scope import head_scope
                    request.managed_scope = head_scope(user)
                return view_func(request, *args, **kwargs)
        return wrapper
    return decorator
