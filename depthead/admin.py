from django.contrib import admin

from .models import CollegeAIInsight


@admin.register(CollegeAIInsight)
class CollegeAIInsightAdmin(admin.ModelAdmin):
    list_display = (
        "college_code",
        "model_name",
        "generated_at",
        "refresh_after",
    )
    search_fields = ("college_code",)
    readonly_fields = (
        "analytics_hash",
        "insights",
        "generated_at",
        "refresh_after",
        "created_at",
        "updated_at",
    )
