from functools import wraps
from django.core.exceptions import PermissionDenied
from .school_scope import ALL_SCHOOLS, require_school, school_scope
from .role_access import can_access_role

def role_required(role):
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            user = request.user
            if not user.is_authenticated or not can_access_role(user, role) or not user.is_active or user.account_status != 'active':
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
                    allowed = (any(has_school_admin_permission(user, item) for item in feature)
                               if isinstance(feature, (tuple, list, set))
                               else has_school_admin_permission(user, feature))
                    if not allowed:
                        raise PermissionDenied('Your School Admin account does not have access to this feature.')
                if role == 'depthead':
                    from apps.depthead.scope import head_scope
                    request.managed_scope = head_scope(user)
                return view_func(request, *args, **kwargs)
        return wrapper
    return decorator
