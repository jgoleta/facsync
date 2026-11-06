from django.urls import path
from . import views
from . import department_views

app_name = 'superadmin'

urlpatterns = [
    path('school-settings/', views.school_settings, name='school_settings'),
    path('', views.superadmin_dashboard, name='superadmin_dashboard'),
    path('dashboard/', views.superadmin_dashboard, name='superadmin_dashboard'),
    path('colleges/', views.manage_colleges, name='manage_colleges'),
    path('departments/', department_views.manage_departments, name='manage_departments'),
    path('departments/create/', department_views.save_department, name='create_department'),
    path('departments/<int:department_id>/edit/', department_views.save_department, name='edit_department'),
    path('departments/<int:department_id>/status/', department_views.department_status, name='department_status'),
    path('departments/<int:department_id>/delete/', department_views.delete_department, name='delete_department'),
    path('admins/invites/<int:invite_id>/edit/', views.edit_head_invite, name='edit_head_invite'),
    path('offices/', views.manage_offices, name='manage_offices'),
    path('admins/', views.manage_admins, name='manage_admins'),
    path('faculty/', views.manage_faculty, name='manage_faculty'),
    path('students/', views.manage_students, name='manage_students'),
    path('invite-depthead/', views.invite_depthead, name='invite_depthead'),
    path('colleges/create/', views.create_college, name='create_college'),
    path('offices/create/', views.create_office, name='create_office'),
    path('offices/<int:office_id>/delete/', views.delete_office, name='delete_office'),
    path('invite-office-admin/', views.invite_office_admin, name='invite_office_admin'),
    path('colleges/<int:college_id>/edit/', views.edit_college, name='edit_college'),
    path('colleges/<int:college_id>/delete/', views.delete_college, name='delete_college'),
    path('admins/depthead/<int:user_id>/edit/', views.edit_depthead, name='edit_depthead'),
    path('admins/depthead/<int:user_id>/remove/', views.remove_depthead, name='remove_depthead'),
    path('invite-faculty/', views.invite_faculty_superadmin, name='invite_faculty_superadmin'),
    path('faculty/<int:user_id>/remove/', views.remove_faculty_superadmin, name='remove_faculty_superadmin'),
    path('faculty/<int:user_id>/assignment/', department_views.assign_faculty, name='assign_faculty'),
    path('students/<int:user_id>/remove/', views.remove_student_superadmin, name='remove_student_superadmin'),
]
