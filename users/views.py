from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAdminUser
from django.contrib.auth import get_user_model
from django.shortcuts import redirect
from rest_framework_simplejwt.tokens import RefreshToken
from django.conf import settings

User = get_user_model()


def google_login_redirect(request):
    """
    Redirects Google-authenticated users to the frontend
    with freshly issued JWT tokens.
    """
    user = request.user

    if not user.is_authenticated:
        # Not logged in — redirect to frontend login page with an error
        return redirect(f"{settings.FRONTEND_URL}/login?error=unauthorized")

    # ✅ Generate JWT tokens for this Google-authenticated user
    refresh = RefreshToken.for_user(user)
    access_token = str(refresh.access_token)

    # ✅ Build frontend callback URL (works for both dev & prod)
    frontend_url = f"{settings.FRONTEND_URL}/auth/callback?access={access_token}&refresh={refresh}"

    return redirect(frontend_url)


class UserAdminViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all()
    permission_classes = [IsAdminUser]  # only admins can access this
    lookup_field = "pk"

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
