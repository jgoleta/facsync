from django.contrib import admin
from .models import StatusEmailDelivery, StatusSchedulerState


@admin.register(StatusEmailDelivery)
class StatusEmailDeliveryAdmin(admin.ModelAdmin):
    list_display = ('id', 'history', 'state', 'attempts', 'reason', 'created_at', 'finished_at')
    list_filter = ('state',)
    readonly_fields = tuple(field.name for field in StatusEmailDelivery._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(StatusSchedulerState)
class StatusSchedulerStateAdmin(admin.ModelAdmin):
    list_display = ('name', 'lease_until', 'faculty_cursor', 'last_finished_at')
    readonly_fields = tuple(field.name for field in StatusSchedulerState._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
