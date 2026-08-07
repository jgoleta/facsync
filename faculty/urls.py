from django.urls import path
from . import views

app_name = 'faculty'

urlpatterns = [
    path('dashboard/', views.dashboard, name='dashboard'),
    path('booking-management/', views.booking_management, name='booking_management'),
    path('schedule/bookingManagement.html', views.booking_management_legacy, name='booking_management_legacy'),
    path('profile/', views.profile, name='profile'),
    path('schedule/', views.schedule, name='schedule'),
]
