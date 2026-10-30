from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.forms import UserChangeForm
from django.core.exceptions import ValidationError
from apps.systemadmin.services import require_replacement_superadmin
from .models import User, FacultyInvite, DeptHeadInvite, OfficeClosure, CollegeAnnouncement


class SystemAwareUserChangeForm(UserChangeForm):
    class Meta(UserChangeForm.Meta):
        model = User

    def clean(self):
        data = super().clean()
        if data.get('role') == 'systemadmin':
            data['school'] = None
            data['college'] = None
        elif not data.get('school'):
            raise ValidationError('School accounts must be assigned to a school.')
        if self.instance.pk:
            prior = User.objects.get(pk=self.instance.pk)
            removes_school_admin = (data.get('role') != 'superadmin' or not data.get('is_active')
                or data.get('account_status') != 'active' or data.get('school') != prior.school)
            if removes_school_admin:
                require_replacement_superadmin(prior)
        return data


class CustomUserAdmin(UserAdmin):
    form = SystemAwareUserChangeForm
    fieldsets = UserAdmin.fieldsets + (
        ('FacSync Info', {'fields': ('role', 'account_status', 'school', 'college')}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ('FacSync Info', {'fields': ('role', 'account_status', 'school', 'college')}),
    )
    list_display = ('username', 'email', 'role', 'account_status', 'is_staff')

admin.site.register(User, CustomUserAdmin)
admin.site.register(FacultyInvite)
admin.site.register(DeptHeadInvite)
admin.site.register(OfficeClosure)
admin.site.register(CollegeAnnouncement)
