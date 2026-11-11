"""School Admin feature permissions, independent of the platform Super Admin role."""
from django.core.exceptions import ValidationError

FEATURES = [('overview', 'School Overview'), ('colleges', 'Manage Colleges'),
    ('departments', 'Manage Departments'), ('offices', 'Manage Offices'),
    ('admins', 'Manage Admin Accounts'), ('faculty', 'Manage Faculty'),
    ('students', 'Manage Students'), ('settings', 'School Settings')]


def default_school_admin_permissions():
    return ['overview', 'colleges', 'departments']


def validate_school_admin_permissions(value):
    if (not isinstance(value, list) or any(not isinstance(key, str) or key not in dict(FEATURES) for key in value)
            or len(value) != len(set(value))):
        raise ValidationError('Select only supported School Admin permissions, without duplicates.')


def has_school_admin_permission(user, feature):
    if (not user.is_authenticated or user.role != 'superadmin' or not user.school_id
            or not user.is_active or user.account_status != 'active'):
        return False
    if user.school_admin_full_access:
        return True
    if feature == 'overview':
        return True
    return feature in dict(FEATURES) and feature in (user.school_admin_permissions or [])


# An unknown future School Admin action is denied to limited accounts until classified.
VIEW_FEATURES = {
    'superadmin_dashboard': 'overview',
    **dict.fromkeys(['create_college', 'edit_college', 'delete_college'], 'colleges'),
    **dict.fromkeys(['manage_departments', 'save_department', 'department_status', 'delete_department'], 'departments'),
    **dict.fromkeys(['manage_offices', 'create_office', 'delete_office'], 'offices'),
    **dict.fromkeys(['manage_admins', 'invite_depthead', 'edit_depthead', 'edit_head_invite', 'remove_depthead',
        'delete_depthead', 'remove_office_admin', 'delete_office_admin', 'invite_office_admin', 'resend_office_admin_invite'], 'admins'),
    **dict.fromkeys(['manage_faculty', 'invite_faculty_superadmin', 'assign_faculty', 'remove_faculty_superadmin', 'delete_faculty_superadmin'], 'faculty'),
    **dict.fromkeys(['manage_students', 'remove_student_superadmin'], 'students'),
    'school_settings': 'settings',
}
VIEW_FEATURES['manage_colleges'] = ('colleges', 'departments')


def feature_access(user):
    result = {key: has_school_admin_permission(user, key) for key, _ in FEATURES}
    result['school_admins'] = has_school_admin_permission(user, 'school_admins')
    return result


def permission_labels(permissions):
    return [label for key, label in FEATURES if key == 'overview' or key in (permissions or [])]
