# users/middleware.py
import uuid
from django.utils.deprecation import MiddlewareMixin

class AssignGuestIdMiddleware(MiddlewareMixin):
    def process_request(self, request):
        # If logged in, identify normally
        if request.user.is_authenticated:
            request.guest_id = None
            return

        # Otherwise, use (or create) a guest_id cookie
        guest_id = request.COOKIES.get("guest_id")
        if not guest_id:
            guest_id = str(uuid.uuid4())
            request.new_guest_id = guest_id
        request.guest_id = guest_id

    def process_response(self, request, response):
        if getattr(request, "new_guest_id", None):
            response.set_cookie(
                "guest_id",
                request.new_guest_id,
                max_age=60 * 60 * 24 * 30,  # 30 days
                httponly=False,
                secure=True,
                samesite="Lax",
            )
        return response
