from django import template

from apps.core.role_access import has_role


register = template.Library()


@register.filter
def user_has_role(user, role):
    return has_role(user, role)
