from django.urls import path, include
from django.contrib import admin
from rest_framework.routers import DefaultRouter
from products.views import (
    ProductViewSet,
    CategoryViewSet,
    ProductImageViewSet,
    download_sample_excel,
    bulk_upload_products,
    # whoami,
)
from orders.views import OrderViewSet, CartViewSet, verify_event_ticket, scan_ticket
from analytics.views import AnalyticsViewSet
from accounts.views import CustomUserDetailsView, CustomUserAdminViewSet
from users.views import google_login_redirect, full_logout
from django.conf import settings
from django.conf.urls.static import static
from django.views.decorators.csrf import csrf_exempt
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from dj_rest_auth.views import LogoutView
from django.http import JsonResponse


# -------------------------------------------------------------------
# Routers
# -------------------------------------------------------------------
router = DefaultRouter()
router.register(r"products", ProductViewSet)
router.register(r"categories", CategoryViewSet)
router.register(r"orders", OrderViewSet, basename="orders")
router.register(r"cart", CartViewSet, basename="cart")
router.register(r"admin/analytics", AnalyticsViewSet, basename="admin-analytics")
router.register(r"product-images", ProductImageViewSet, basename="product-images")
router.register(r"admin/users", CustomUserAdminViewSet, basename="admin-users")


# -------------------------------------------------------------------
# URL Patterns
# -------------------------------------------------------------------
urlpatterns = [
    # Django Admin
    path("admin/", admin.site.urls),

    path("api/contact/", include(("contact.urls", "contact"))),
    path("api/events/verify/<uuid:code>/", verify_event_ticket, name="verify-ticket"),
    path("api/events/scan/<uuid:code>/", scan_ticket),

    # 🔐 JWT Authentication
    path("api/auth/token/", TokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("api/auth/token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),

    # 👤 Current user (used by fetchCurrentUser)
    path("api/auth/user/", CustomUserDetailsView.as_view(), name="rest_user_details"),
    
    # 🧩 dj-rest-auth (registration, password reset, etc.)
    path("api/auth/", include("dj_rest_auth.urls")),
    path("api/auth/registration/", include("dj_rest_auth.registration.urls")),


    # 🚪 Logout (handled client-side but exposed for safety)
    path("api/auth/logout/", csrf_exempt(LogoutView.as_view()), name="rest_logout"),
    path("api/auth/full-logout/", full_logout, name="full_logout"),

    # 🩺 Health check
    path("api/health/", lambda request: JsonResponse({"status": "ok"}), name="health_check"),

    # 🧮 Misc endpoints
    # path("api/whoami/", whoami),
    path("api/products/download-sample-excel/", download_sample_excel, name="download-sample-excel"),
    path("api/products/bulk-upload/", bulk_upload_products, name="bulk-upload-products"),

    # 🌐 Google OAuth login + redirect
    path("accounts/", include("allauth.urls")),
    path("accounts/profile/", google_login_redirect, name="account_profile_redirect"),

    # 🧠 Users app (if you have custom user routes)
    path("api/users/", include("users.urls")),

    # 🔁 API routers (main app endpoints)
    path("api/", include(router.urls)),
]

# -------------------------------------------------------------------
# Media serving (development only)
# -------------------------------------------------------------------
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
