from django.urls import path
from . import school_onboarding_previews

app_name = 'school_onboarding_preview'
urlpatterns = [
    path('', school_onboarding_previews.preview_index, name='index'),
    path('<str:stage>/', school_onboarding_previews.preview_stage, name='stage'),
]
