from django.urls import path
from . import views

app_name = 'depthead'

urlpatterns = [
    path('', views.admin_dashboard, name='admin_dashboard'),
    path('dashboard/', views.admin_dashboard, name='admin_dashboard'),
    path('adminDashboard', views.admin_dashboard, name='admin_dashboard_legacy'),
    path('faculty/', views.admin_faculty, name='admin_faculty'),
    path('adminFaculty', views.admin_faculty, name='admin_faculty_legacy'),
    path('student-behavior/', views.student_behavior, name='student_behavior'),
    path('studentBehavior', views.student_behavior, name='student_behavior_legacy'),
    path('faculty-monitoring/', views.faculty_monitoring, name='faculty_monitoring'),
    path('facultyMonitoring', views.faculty_monitoring, name='faculty_monitoring_legacy'),
    path('department-settings/', views.department_settings, name='department_settings'),
    path('departmentSettings', views.department_settings, name='department_settings_legacy'),
    path('peak-analytics/', views.peak_analytics, name='peak_analytics'),
    path('peakAnalytics', views.peak_analytics, name='peak_analytics_legacy'),
    path('faculty-trends/', views.faculty_trends, name='faculty_trends'),
    path('facultyTrends', views.faculty_trends, name='faculty_trends_legacy'),
]
