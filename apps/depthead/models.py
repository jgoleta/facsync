from django.db import models


class CollegeAIInsight(models.Model):
    """Persisted Gemini interpretation for one college analytics scope."""

    college_code = models.CharField(max_length=100, unique=True)
    analytics_hash = models.CharField(max_length=64)
    insights = models.JSONField()
    model_name = models.CharField(max_length=100)
    generated_at = models.DateTimeField()
    refresh_after = models.DateTimeField(db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("college_code",)

    def __str__(self):
        return f"{self.college_code} AI insights"
