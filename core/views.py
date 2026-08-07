from django.shortcuts import render

def landing_page(request):
    return render(request, 'core/landingPage.html')

def login_page(request):
    return render(request, 'core/loginPage.html')

def register_page(request):
    return render(request, 'core/registerPage.html')

def dashboard_public(request):
    return render(request, 'core/dashboardPublic.html')