from django.urls import path
from . import views
from . import request_views
from . import onboarding_views

app_name = 'systemadmin'
urlpatterns = [
    path('requests/inquiries/<uuid:inquiry_id>/', onboarding_views.inquiry_review, name='inquiry_review'),
    path('requests/inquiries/<uuid:inquiry_id>/document/', onboarding_views.inquiry_document, name='inquiry_document'),
    path('requests/', request_views.school_requests, name='school_requests'),
    path('requests/<uuid:request_id>/', request_views.request_review, name='request_review'),
    path('', views.manage_school, name='manage_school'),
    path('overview/', views.overview, name='overview'),
    path('schools/add/', views.school_edit, name='school_add'),
    path('schools/<int:school_id>/edit/', views.school_edit, name='school_edit'),
    path('schools/<int:school_id>/status/', views.school_status, name='school_status'),
    path('superadmins/', views.manage_schooladmins, name='manage_schooladmins'),
    path('superadmins/invite/', views.invite_edit, name='invite_add'),
    path('superadmins/invites/<int:invite_id>/edit/', views.invite_edit, name='invite_edit'),
    path('superadmins/invites/<int:invite_id>/status/', views.invite_status, name='invite_status'),
    path('superadmins/invites/<int:invite_id>/resend/', views.invite_resend, name='invite_resend'),
    path('superadmins/<int:user_id>/edit/', views.superadmin_edit, name='superadmin_edit'),
    path('superadmins/<int:user_id>/status/', views.superadmin_status, name='superadmin_status'),
]
