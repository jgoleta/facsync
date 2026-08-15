from django.urls import path
from . import views

app_name = 'students'

urlpatterns = [
    path('dashboard/', views.dashboard, name='dashboard'),
    path('home/', views.home, name='home'),
    path('view-schedule/', views.view_schedule, name='view_schedule'),
    path('consultation-requests/', views.consultation_requests, name='consultation_requests'),
    path('api/walk-ins/status/', views.api_walk_in_status, name='api_walk_in_status'),
    path('api/walk-ins/join/', views.api_join_walk_in_queue, name='api_join_walk_in_queue'),
    path('api/faculty-statuses/', views.api_faculty_statuses, name='api_faculty_statuses'),
]
