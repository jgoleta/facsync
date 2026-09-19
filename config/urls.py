"""
URL configuration for the FacSync project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.conf import settings
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/', include('allauth.urls')),
    path('', include('apps.core.urls')),   #landing page is deafault "/"
    path('student/', include('apps.students.urls')),
    path('faculty/', include('apps.faculty.urls')),
    path('depthead/', include('apps.depthead.urls')),
    path('superadmin/', include('apps.superadmin.urls')),
]

# The app check also keeps these URLs out of production/test settings, even
# when the shared base configuration has DEBUG enabled.
if settings.DEBUG and 'debug_toolbar' in settings.INSTALLED_APPS:
    from debug_toolbar.toolbar import debug_toolbar_urls
    urlpatterns += debug_toolbar_urls()

