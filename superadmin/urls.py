from django.urls import path
from . import views

app_name = 'superadmin'

urlpatterns = [
    path('', views.superadmin_dashboard, name='superadmin_dashboard'),
    path('dashboard/', views.superadmin_dashboard, name='superadmin_dashboard'),
    path('colleges/', views.manage_colleges, name='manage_colleges'),
    path('admins/', views.manage_admins, name='manage_admins'),
    path('faculty/', views.manage_faculty, name='manage_faculty'),
    path('students/', views.manage_students, name='manage_students'),
    path('invite-depthead/', views.invite_depthead, name='invite_depthead'),
    path('colleges/create/', views.create_college, name='create_college'),
    path('colleges/<int:college_id>/edit/', views.edit_college, name='edit_college'),
    path('colleges/<int:college_id>/delete/', views.delete_college, name='delete_college'),
    path('admins/depthead/<int:user_id>/edit/', views.edit_depthead, name='edit_depthead'),
    path('admins/depthead/<int:user_id>/remove/', views.remove_depthead, name='remove_depthead'),
    path('invite-faculty/', views.invite_faculty_superadmin, name='invite_faculty_superadmin'),
    path('faculty/<int:user_id>/remove/', views.remove_faculty_superadmin, name='remove_faculty_superadmin'),
    path('students/<int:user_id>/remove/', views.remove_student_superadmin, name='remove_student_superadmin'),
]
