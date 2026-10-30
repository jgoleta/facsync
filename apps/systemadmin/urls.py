from django.urls import path
from . import views

app_name = 'systemadmin'
urlpatterns = [
    path('', views.manage_schools, name='manage_schools'),
    path('schools/add/', views.school_edit, name='school_add'),
    path('schools/<int:school_id>/edit/', views.school_edit, name='school_edit'),
    path('schools/<int:school_id>/status/', views.school_status, name='school_status'),
    path('superadmins/', views.manage_superadmins, name='manage_superadmins'),
    path('superadmins/invite/', views.invite_edit, name='invite_add'),
    path('superadmins/invites/<int:invite_id>/edit/', views.invite_edit, name='invite_edit'),
    path('superadmins/invites/<int:invite_id>/status/', views.invite_status, name='invite_status'),
    path('superadmins/invites/<int:invite_id>/resend/', views.invite_resend, name='invite_resend'),
    path('superadmins/<int:user_id>/edit/', views.superadmin_edit, name='superadmin_edit'),
    path('superadmins/<int:user_id>/status/', views.superadmin_status, name='superadmin_status'),
]
