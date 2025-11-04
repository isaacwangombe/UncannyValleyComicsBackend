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
    user = request.user

    # 🧩 If not logged in via Google
    if not user.is_authenticated:
        return redirect(f"{settings.FRONTEND_URL}/login?error=unauthorized")

    # 🪙 Generate JWTs for Google-authenticated user
    try:
        refresh = RefreshToken.for_user(user)
        access_token = str(refresh.access_token)
        refresh_token = str(refresh)
    except Exception as e:
        print("❌ Error generating JWT:", e)
        return redirect(f"{settings.FRONTEND_URL}/login?error=token_failed")

    # 🧠 Build the exact redirect URL
    redirect_url = (
        f"{settings.FRONTEND_URL}/auth/callback"
        f"?access={access_token}&refresh={refresh_token}"
    )

    print("🔁 Redirecting Google user to:", redirect_url)
    return redirect(redirect_url)



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
