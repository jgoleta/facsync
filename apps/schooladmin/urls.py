from django.urls import path
from . import views
from . import department_views
from . import schooladmin_views
from . import directory_views

app_name = 'superadmin'

urlpatterns = [
    path('colleges/<int:college_id>/status/', directory_views.college_status, name='college_status'),
    path('offices/<int:office_id>/status/', directory_views.office_status, name='office_status'),
    path('superadmins/<int:user_id>/permissions/', schooladmin_views.edit_school_admin_permissions, name='edit_school_admin_permissions'),
    path('superadmins/invites/<int:invite_id>/permissions/', schooladmin_views.edit_school_admin_invite_permissions, name='edit_school_admin_invite_permissions'),
    path('superadmins/', schooladmin_views.manage_superadmins, name='manage_superadmins'),
    path('superadmins/invite/', schooladmin_views.invite_superadmin, name='invite_superadmin'),
    path('superadmins/invites/<int:invite_id>/resend/', schooladmin_views.resend_superadmin_invite, name='resend_superadmin_invite'),
    path('superadmins/invites/<int:invite_id>/cancel/', schooladmin_views.cancel_superadmin_invite, name='cancel_superadmin_invite'),
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
    path('office-admin-invites/<int:invite_id>/resend/', views.resend_office_admin_invite, name='resend_office_admin_invite'),
    path('colleges/<int:college_id>/edit/', views.edit_college, name='edit_college'),
    path('colleges/<int:college_id>/delete/', views.delete_college, name='delete_college'),
    path('admins/depthead/<int:user_id>/edit/', views.edit_depthead, name='edit_depthead'),
    path('admins/depthead/<int:user_id>/remove/', views.remove_depthead, name='remove_depthead'),
    path('admins/depthead/<int:user_id>/delete/', views.delete_depthead, name='delete_depthead'),
    path('admins/office/<int:user_id>/remove/', views.remove_office_admin, name='remove_office_admin'),
    path('admins/office/<int:user_id>/delete/', views.delete_office_admin, name='delete_office_admin'),
    path('invite-faculty/', views.invite_faculty_superadmin, name='invite_faculty_superadmin'),
    path('faculty/<int:user_id>/remove/', views.remove_faculty_superadmin, name='remove_faculty_superadmin'),
    path('faculty/<int:user_id>/delete/', views.delete_faculty_superadmin, name='delete_faculty_superadmin'),
    path('faculty/<int:user_id>/assignment/', department_views.assign_faculty, name='assign_faculty'),
    path('students/<int:user_id>/remove/', views.remove_student_superadmin, name='remove_student_superadmin'),
]
