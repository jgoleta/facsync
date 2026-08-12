from django.urls import path
from . import views

app_name = 'faculty'

urlpatterns = [
    path('dashboard/', views.dashboard, name='dashboard'),
    path('api/status/', views.update_status, name='update_status'),
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
