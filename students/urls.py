from django.urls import path
from . import views

app_name = 'students'

urlpatterns = [
    path('dashboard/', views.dashboard, name='dashboard'),
    path('book-consultation/', views.book_consultation, name='book_consultation'),
    path('view-schedule/', views.view_schedule, name='view_schedule'),
    path('consultation-requests/', views.consultation_requests, name='consultation_requests'),
]