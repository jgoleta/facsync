import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'facsync_project.settings')
import django
django.setup()
from django.conf import settings
import smtplib

server = smtplib.SMTP(settings.EMAIL_HOST, settings.EMAIL_PORT)
server.starttls()
server.login(settings.EMAIL_HOST_USER, settings.EMAIL_HOST_PASSWORD)
print("Login successful!")
server.quit()