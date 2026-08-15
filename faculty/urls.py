from django.urls import path
from . import views

app_name = 'faculty'

urlpatterns = [
    path('dashboard/', views.dashboard, name='dashboard'),
    path('api/status/', views.update_status, name='update_status'),
    path('api/walk-ins/preference/', views.api_walk_in_preference, name='api_walk_in_preference'),
    path('api/walk-ins/', views.api_faculty_walk_ins, name='api_faculty_walk_ins'),
    path('api/walk-ins/<str:queue_id>/', views.api_walk_in_detail, name='api_walk_in_detail'),
    path('booking-management/', views.booking_management, name='booking_management'),
    path('schedule/bookingManagement.html', views.booking_management_legacy, name='booking_management_legacy'),
    path('profile/', views.profile, name='profile'),
    path('schedule/', views.schedule, name='schedule'),
    path('calendar/connect/', views.calendar_connect, name='calendar_connect'),
    path('calendar/callback/', views.calendar_callback, name='calendar_callback'),
    path('calendar/disconnect/', views.calendar_disconnect, name='calendar_disconnect'),
    path('api/calendar/status/', views.calendar_status, name='calendar_status'),
    path('api/calendar/preference/', views.calendar_preference, name='calendar_preference'),
    # API for schedule events
    path('api/events/', views.api_schedule_events, name='api_schedule_events'),
    path('api/events/<int:pk>/', views.api_schedule_event_detail, name='api_schedule_event_detail'),
    path('api/consultations/<str:request_id>/', views.api_consultation, name='api_consultation'),
]
