from django.apps import AppConfig

class CoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.core'

    def ready(self):
        from allauth.socialaccount.signals import pre_social_login
        from .signals import google_login_domain_check
        pre_social_login.connect(google_login_domain_check)
        from django.db.models.signals import post_delete
        from .models import User
        from .signals import cleanup_user_photo
        post_delete.connect(cleanup_user_photo, sender=User, dispatch_uid='core.cleanup_user_photo')
