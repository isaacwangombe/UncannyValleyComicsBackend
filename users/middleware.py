from allauth.socialaccount import app_settings

class ClearAllauthCacheMiddleware:
    """
    Clears the in-memory SocialApp cache before each request.
    Prevents stale duplicate objects in allauth._apps cache.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Clear cached app registry (safe, very light)
        if hasattr(app_settings, "_apps"):
            app_settings._apps.clear()
        return self.get_response(request)
