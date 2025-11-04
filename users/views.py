from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAdminUser, AllowAny
from django.contrib.auth import get_user_model
from django.shortcuts import redirect
from rest_framework_simplejwt.tokens import RefreshToken
from django.conf import settings
from django.contrib.auth import logout as django_logout
from rest_framework.decorators import api_view, permission_classes


User = get_user_model()

def google_login_redirect(request):
    user = request.user
    if not user.is_authenticated:
        return redirect(f"{settings.FRONTEND_URL}/login?error=unauthorized")

    # ✅ Generate JWT tokens for this Google-authenticated user
    refresh = RefreshToken.for_user(user)
    access_token = str(refresh.access_token)
    refresh_token = str(refresh)

    # ✅ Redirect to frontend with tokens in query params
    frontend_url = (
        f"{settings.FRONTEND_URL}/auth/callback"
        f"?access={access_token}&refresh={refresh_token}"
    )

    return redirect(frontend_url)

@api_view(["POST"])
@permission_classes([AllowAny])
def full_logout(request):
    """Fully log out user and clear session cookies"""
    django_logout(request)
    response = JsonResponse({"detail": "Successfully logged out."})
    response.delete_cookie("sessionid")
    response.delete_cookie("csrftoken")
    return response


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
