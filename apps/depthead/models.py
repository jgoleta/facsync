from django.db import models
from apps.core.school_scope import SchoolScopedModel


class CollegeAIInsight(SchoolScopedModel):
    """Persisted Gemini interpretation for one college analytics scope."""

    school = models.ForeignKey('core.School', on_delete=models.PROTECT, null=True, blank=True, related_name='ai_insights')
    college_code = models.CharField(max_length=100)
    analytics_hash = models.CharField(max_length=64)
    insights = models.JSONField()
    model_name = models.CharField(max_length=100)
    generated_at = models.DateTimeField()
    refresh_after = models.DateTimeField(db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("college_code",)
        constraints = [models.UniqueConstraint(models.functions.Lower('college_code'), models.F('school'), name='insight_school_college_unique')]

    def __str__(self):
        return f"{self.college_code} AI insights"
