# users/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import UserAdminViewSet, get_csrf_token  # ✅ import from views

router = DefaultRouter()
router.register(r'admin/users', UserAdminViewSet, basename='admin-users')

urlpatterns = [
    # ✅ Use the get_csrf_token view defined in views.py
    path("set-csrf/", get_csrf_token, name="set-csrf"),
    path("", include(router.urls)),
]
