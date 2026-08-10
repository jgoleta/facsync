from django.urls import path
from . import views

app_name = 'core'

urlpatterns = [
    path('', views.landing_page, name='landing'),
    path('login/', views.login_page, name='login'),
    path('register/', views.register_page, name='register'),
    path('public-dashboard/', views.dashboard_public, name='dashboard_public'),
    path('register/student/', views.register_student, name='register_student'),
    path('register/faculty/', views.register_faculty, name='register_faculty'),
    path('register/faculty/pending/', views.faculty_pending_registration, name='faculty_pending_registration'),
    
]