from django import template

from apps.core.role_access import has_role, active_role, available_roles, can_access_role


register = template.Library()


@register.filter
def user_has_role(user, role):
    return has_role(user, role)


@register.filter
def user_can_access_role(user, role):
    return can_access_role(user, role)


@register.simple_tag
def current_workspace(request):
    return active_role(request)


@register.simple_tag
def available_user_roles(user):
    return available_roles(user)
