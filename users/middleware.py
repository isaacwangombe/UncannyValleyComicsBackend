# users/middleware.py
from allauth.socialaccount import app_settings

class ClearAllauthCacheMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path.startswith("/accounts/"):
            print("ClearAllauthCacheMiddleware: clearing Allauth cache for", request.path)
            cache = getattr(app_settings, "_apps", None)
            print("  before clear, app_settings._apps is", type(cache), "len:", (len(cache) if isinstance(cache, dict) else "NA"))
            if isinstance(cache, dict):
                cache.clear()
            # also ensure attribute exists
            if not hasattr(app_settings, "_apps"):
                app_settings._apps = {}
            print("  after clear, app_settings._apps:", app_settings._apps)
        return self.get_response(request)
