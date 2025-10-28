from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAdminUser
from django.contrib.auth import get_user_model
from django.shortcuts import redirect
from django.conf import settings
from django.views.decorators.csrf import ensure_csrf_cookie
from django.http import JsonResponse
from django.views.decorators.clickjacking import xframe_options_exempt
from django.views.decorators.http import require_GET

User = get_user_model()


@require_GET
@ensure_csrf_cookie
@xframe_options_exempt
def get_csrf_token(request):
    """Return a fresh CSRF token and set cookie"""
    response = JsonResponse({"detail": "CSRF cookie set."})
    response["Access-Control-Allow-Origin"] = "https://uncannyvalleycomics.netlify.app"
    response["Access-Control-Allow-Credentials"] = "true"
    return response


def google_login_redirect(request):
    """
    Redirect users to the frontend after successful Google login.
    """
    # Use the FRONTEND_URL from settings or default to localhost
    frontend_url = getattr(settings, "FRONTEND_URL", "http://127.0.0.1:5173")
    # Redirect to /admin page (you can change to "/" or another route if you prefer)
    return redirect(frontend_url + "/admin")


class UserAdminViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all()
    permission_classes = [IsAdminUser]  # only admins can access this
    lookup_field = "pk"  # allows URLs like /api/admin/users/5/

    @action(detail=True, methods=["post"])
    def make_staff(self, request, pk=None):
        """Grant staff status to a user"""
        user = self.get_object()
        user.is_staff = True
        user.save(update_fields=["is_staff"])
        return Response(
            {"detail": f"{user.username} is now a staff member."},
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=["post"])
    def remove_staff(self, request, pk=None):
        """Remove staff status from a user"""
        user = self.get_object()
        user.is_staff = False
        user.save(update_fields=["is_staff"])
        return Response(
            {"detail": f"{user.username} is no longer a staff member."},
            status=status.HTTP_200_OK,
        )
