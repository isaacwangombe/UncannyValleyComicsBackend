from django.urls import path, include
from django.contrib import admin
from rest_framework.routers import DefaultRouter
from products.views import ProductViewSet, CategoryViewSet,ProductImageViewSet, download_sample_excel,bulk_upload_products, whoami  
from orders.views import OrderViewSet, CartViewSet
from analytics.views import AnalyticsViewSet
from users.views import google_login_redirect
from accounts.views import CustomUserDetailsView, CustomUserAdminViewSet
from django.conf import settings
from django.conf.urls.static import static
from . import views
from django.views.decorators.csrf import csrf_exempt
from dj_rest_auth.views import LogoutView

router = DefaultRouter()
router.register(r"products", ProductViewSet)
router.register(r"categories", CategoryViewSet)
router.register(r"orders", OrderViewSet, basename="orders")
router.register(r"cart", CartViewSet, basename="cart")
router.register(r"admin/analytics", AnalyticsViewSet, basename="admin-analytics")
router.register(r"product-images", ProductImageViewSet, basename="product-images")
router.register(r"admin/users", CustomUserAdminViewSet, basename="admin-users")
router.register(r'product-images', ProductImageViewSet, basename='productimage')


urlpatterns = [
    path("api/whoami/", whoami),
    path("api/auth/logout/", csrf_exempt(LogoutView.as_view()), name="rest_logout"),

    path("admin/", admin.site.urls),
    path("api/auth/user/", CustomUserDetailsView.as_view(), name="rest_user_details"),

    path("api/health/", views.health_check, name="health_check"),

    #  Download sample Excel for bulk upload
    
    path("api/products/download-sample-excel/", download_sample_excel, name="download-sample-excel"),
    path("api/products/bulk-upload/", bulk_upload_products, name="bulk-upload-products"),

    # Auth routes
    path("api/auth/", include("dj_rest_auth.urls")),
    path("api/auth/registration/", include("dj_rest_auth.registration.urls")),

    # Google login redirect
    path("accounts/", include("allauth.urls")),
    path("accounts/profile/", google_login_redirect, name="account_profile_redirect"),

    # ✅ Include your users app (which contains set-csrf)
    path("api/users/", include("users.urls")),

    # Routers
    path("api/", include(router.urls)),
]

urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
