from django.apps import AppConfig

class UsersConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "users"

    def ready(self):
        from django.db import connection
        if connection.settings_dict.get("NAME"):
            try:
                from allauth.socialaccount.models import SocialApp
                from django.contrib.sites.models import Site
                from django.conf import settings

                site = Site.objects.get(id=settings.SITE_ID)
                apps_qs = SocialApp.objects.filter(provider="google")
                if apps_qs.count() > 1:
                    print("⚠️ Found multiple Google apps — cleaning up.")
                    apps_qs.exclude(id=apps_qs.first().id).delete()
                app = apps_qs.first()
                if app and site not in app.sites.all():
                    app.sites.set([site])
                print("✅ SocialApp sanity check complete.")
            except Exception as e:
                print("⚠️ SocialApp sanity check skipped:", e)
