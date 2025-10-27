from rest_framework import permissions

class IsAdminOrReadOnly(permissions.BasePermission):
    """
    Custom permission to only allow admins to edit products.
    Non-admins can only view (GET, HEAD, OPTIONS).
    """

    def has_permission(self, request, view):
        # SAFE_METHODS are GET, HEAD, OPTIONS → read-only access
        if request.method in permissions.SAFE_METHODS:
            return True
        # Otherwise, must be admin/staff
        return request.user and request.user.is_staff
