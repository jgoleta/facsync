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
    path('invite-depthead/', views.invite_depthead, name='invite_depthead'),
    path('departments/create/', views.create_department, name='create_department'),
    path('departments/<int:department_id>/edit/', views.edit_department, name='edit_department'),
    path('departments/<int:department_id>/delete/', views.delete_department, name='delete_department'),
    path('admins/depthead/<int:user_id>/edit/', views.edit_depthead, name='edit_depthead'),
    path('admins/depthead/<int:user_id>/remove/', views.remove_depthead, name='remove_depthead'),
    path('invite-faculty/', views.invite_faculty_superadmin, name='invite_faculty_superadmin'),
    path('faculty/<int:user_id>/remove/', views.remove_faculty_superadmin, name='remove_faculty_superadmin'),
    path('students/<int:user_id>/remove/', views.remove_student_superadmin, name='remove_student_superadmin'),
]
