from django.urls import path
from . import views

app_name = 'depthead'

urlpatterns = [
    path('', views.admin_dashboard, name='admin_dashboard'),
    path('dashboard/', views.admin_dashboard, name='admin_dashboard'),
    path('adminDashboard', views.admin_dashboard, name='admin_dashboard_legacy'),
    path('adminFaculty', views.admin_faculty, name='admin_faculty'),
    path('student-behavior/', views.student_behavior, name='student_behavior'),
    path('studentBehavior', views.student_behavior, name='student_behavior_legacy'),
    path('faculty-monitoring/', views.faculty_monitoring, name='faculty_monitoring'),
    path('facultyMonitoring', views.faculty_monitoring, name='faculty_monitoring_legacy'),
    path('college-settings/', views.college_settings, name='college_settings'),
    path('collegeSettings', views.college_settings, name='college_settings_legacy'),
    path('peak-analytics/', views.peak_analytics, name='peak_analytics'),
    path('peakAnalytics', views.peak_analytics, name='peak_analytics_legacy'),
    path('faculty-trends/', views.faculty_trends, name='faculty_trends'),
    path('facultyTrends', views.faculty_trends, name='faculty_trends_legacy'),
    path('adminFaculty/<int:user_id>/approve/', views.approve_faculty, name='approve_faculty'),
    path('adminFaculty/<int:user_id>/decline/', views.decline_faculty, name='decline_faculty'),
    path('adminFaculty/invite/', views.invite_faculty, name='invite_faculty'),
    path('adminFaculty/<int:user_id>/remove/', views.remove_faculty, name='remove_faculty'),
    path('adminFaculty/schedule/template/', views.faculty_schedule_template, name='faculty_schedule_template'),
    path('adminFaculty/<str:faculty_id>/schedule/upload/', views.upload_faculty_schedule, name='upload_faculty_schedule'),
    path('adminFaculty/<str:faculty_id>/schedule/preview/', views.view_faculty_schedule_preview, name='view_faculty_schedule_preview'),
    path('adminFaculty/<str:faculty_id>/schedule/delete/', views.delete_faculty_schedule, name='delete_faculty_schedule'),
    path('announcements/create/', views.create_announcement, name='create_announcement'),
    path('college/edit-description/', views.edit_college_description, name='edit_college_description'),
    path('faculty-monitoring/data/', views.faculty_monitoring_data, name='faculty_monitoring_data'),
]
