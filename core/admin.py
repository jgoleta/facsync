from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User, FacultyInvite, DeptHeadInvite, OfficeClosure, CollegeAnnouncement


class CustomUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        ('FacSync Info', {'fields': ('role', 'account_status', 'college')}),
    )
    list_display = ('username', 'email', 'role', 'account_status', 'is_staff')

admin.site.register(User, CustomUserAdmin)
admin.site.register(FacultyInvite)
admin.site.register(DeptHeadInvite)
admin.site.register(OfficeClosure)
admin.site.register(CollegeAnnouncement)