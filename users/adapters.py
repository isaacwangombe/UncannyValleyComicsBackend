# users/adapters.py

from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from allauth.socialaccount.models import SocialApp
from django.shortcuts import redirect
from django.conf import settings
from django.contrib.sites.models import Site
from django.core.exceptions import ObjectDoesNotExist


class SafeSocialAccountAdapter(DefaultSocialAccountAdapter):
    """
    Fixes the MultipleObjectsReturned bug in Allauth
    AND preserves your frontend redirect behavior.
    """

    def get_app(self, request, provider, client_id=None):
        """
        Allauth override: ensures only one SocialApp is returned per provider.
        Fixes race/duplication issues when multiple Site objects are cached.
        """
        try:
            current_site = Site.objects.get_current(request)
        except Exception:
            current_site = None

        site_id = getattr(current_site, "id", None)
        qs = SocialApp.objects.filter(provider=provider)
        if site_id:
            qs = qs.filter(sites__id=site_id)

        count = qs.count()
        if count == 0:
            raise ObjectDoesNotExist(f"No SocialApp found for provider {provider}")
        elif count > 1:
            # Log a warning but continue gracefully
            print(f"⚠️ SafeSocialAccountAdapter: Found {count} SocialApps for {provider}, using first.")

        app = qs.first()
        return app

    # ✅ Your original redirect logic stays here
    def get_login_redirect_url(self, request):
        """
        Forces a redirect to the frontend URL configured in settings,
        ensuring a 302 response is issued to the browser.
        """
        url = getattr(settings, 'LOGIN_REDIRECT_URL', getattr(settings, 'FRONTEND_URL', '/'))
        return url

    def socialaccount_login_success(self, request, socialaccount):
        """
        This method is called upon successful login. Explicitly
        redirects to the frontend after login.
        """
        return redirect(self.get_login_redirect_url(request))
