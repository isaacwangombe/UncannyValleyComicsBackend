# users/adapters.py

from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.shortcuts import redirect
from django.conf import settings

class SafeSocialAccountAdapter(DefaultSocialAccountAdapter):
    
    # This method is called after a successful social login/signup
    def get_login_redirect_url(self, request):
        """
        Forces a redirect to the frontend URL configured in settings,
        ensuring a 302 response is issued to the browser.
        """
        # Retrieve the URL from settings, falling back to a safe default
        url = getattr(settings, 'LOGIN_REDIRECT_URL', settings.FRONTEND_URL)
        
        # Ensure we always return the redirect path
        return url

    # Optional but highly recommended: Overwrite the response after login/connect
    def socialaccount_login_success(self, request, socialaccount):
        """
        This method is called upon successful login. We can explicitly 
        issue the redirect here to ensure a 302 response is returned.
        """
        return redirect(self.get_login_redirect_url(request))