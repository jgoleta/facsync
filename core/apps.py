from django.apps import AppConfig

class CoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'core'

    def ready(self):
        from allauth.socialaccount.signals import pre_social_login
        from .signals import google_login_domain_check
        pre_social_login.connect(google_login_domain_check)