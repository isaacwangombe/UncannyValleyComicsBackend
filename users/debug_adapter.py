from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from allauth.socialaccount.models import SocialApp
from django.contrib.sites.models import Site

class DebugSocialAccountAdapter(DefaultSocialAccountAdapter):
    """Temporarily prints what get_app() finds."""

    def get_app(self, request, provider):
        site = Site.objects.get_current(request)
        qs = SocialApp.objects.filter(provider=provider, sites=site)
        print("⚙️ DEBUG get_app(): provider=", provider)
        print("  current site:", site.id, site.domain)
        print("  queryset count:", qs.count())
        for app in qs:
            print("  -> id:", app.id, "name:", app.name, "sites:", [s.domain for s in app.sites.all()])
        # provider-only fallback
        fallback = SocialApp.objects.filter(provider=provider)
        print("  fallback count (provider only):", fallback.count())
        for f in fallback:
            print("  fallback -> id:", f.id, "sites:", [s.domain for s in f.sites.all()])
        return super().get_app(request, provider)
