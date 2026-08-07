from django.urls import path
from . import views

app_name = 'superadmin'

urlpatterns = [
    path('', views.superadmin_dashboard, name='superadmin_dashboard'),
    path('dashboard/', views.superadmin_dashboard, name='superadmin_dashboard'),
    path('departments/', views.manage_departments, name='manage_departments'),
    path('admins/', views.manage_admins, name='manage_admins'),
    path('faculty/', views.manage_faculty, name='manage_faculty'),
    path('students/', views.manage_students, name='manage_students'),
]
