# accounts/views.py
from dj_rest_auth.views import UserDetailsView
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from .serializers import CustomUserDetailsSerializer

User = get_user_model()


def is_owner(user):
    """Helper: check if user belongs to 'Owner' group"""
    return user.groups.filter(name="Owner").exists()


# ---------------------------------------------------------------------
# ✅ 1️⃣ Simple user details endpoint
# ---------------------------------------------------------------------
class CustomUserDetailsView(UserDetailsView):
    """Keeps /api/auth/user/ working correctly"""
    serializer_class = CustomUserDetailsSerializer


# ---------------------------------------------------------------------
# ✅ 2️⃣ Admin / Owner Management ViewSet
# ---------------------------------------------------------------------
class CustomUserAdminViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Superadmins and Owners can manage users.
    - Superadmin: sees everyone
    - Owner: sees everyone except superadmins
    - Others: see themselves
    """
    queryset = User.objects.all()
    serializer_class = CustomUserDetailsSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user

        # Superadmins see everyone
        if user.is_superuser:
            return User.objects.all()

        # Owners see everyone except superadmins
        if is_owner(user):
            return User.objects.filter(is_superuser=False)

        # Staff/customers can only see themselves
        return User.objects.filter(pk=user.pk)

    # -----------------------------------------------------------------
    # ROLE MANAGEMENT ACTIONS
    # -----------------------------------------------------------------
    @action(detail=True, methods=["post"], permission_classes=[permissions.IsAuthenticated])
    def toggle_staff(self, request, pk=None):
        """Toggle staff status (Owner & Superadmin only)"""
        current_user = request.user
        target_user = self.get_object()

        # 🧩 Prevent self-edit
        if current_user.pk == target_user.pk:
            return Response(
                {"detail": "You cannot modify your own status."},
                status=status.HTTP_403_FORBIDDEN,
            )

        # 🧩 Restrict who can edit
        if not (current_user.is_superuser or is_owner(current_user)):
            return Response(
                {"detail": "Not authorized to change staff roles."},
                status=status.HTTP_403_FORBIDDEN,
            )

        # 🧩 Owners cannot modify superadmins
        if target_user.is_superuser and not current_user.is_superuser:
            return Response(
                {"detail": "Owners cannot modify Superadmins."},
                status=status.HTTP_403_FORBIDDEN,
            )

        # 🧩 Toggle staff
        target_user.is_staff = not target_user.is_staff
        target_user.save(update_fields=["is_staff"])

        return Response(
            {"detail": f"{target_user.email} staff status set to {target_user.is_staff}."}
        )

    @action(detail=True, methods=["post"], permission_classes=[permissions.IsAuthenticated])
    def promote_to_owner(self, request, pk=None):
        """Superadmins can promote/demote users to/from Owner group"""
        current_user = request.user
        target_user = self.get_object()

        # 🧩 Prevent self-edit
        if current_user.pk == target_user.pk:
            return Response(
                {"detail": "You cannot modify your own role."},
                status=status.HTTP_403_FORBIDDEN,
            )

        # 🧩 Only superadmins can manage owners
        if not current_user.is_superuser:
            return Response(
                {"detail": "Only Superadmins can promote to Owner."},
                status=status.HTTP_403_FORBIDDEN,
            )

        owner_group, _ = Group.objects.get_or_create(name="Owner")

        if target_user.groups.filter(name="Owner").exists():
            # Demote owner
            target_user.groups.remove(owner_group)
            message = f"{target_user.email} removed from Owner group."
        else:
            # Promote to owner → auto becomes staff
            target_user.groups.add(owner_group)
            target_user.is_staff = True
            target_user.save(update_fields=["is_staff"])
            message = f"{target_user.email} promoted to Owner and made Staff."

        return Response({"detail": message})
