from django.urls import path
from .views import dashboard_stats

urlpatterns = [
    path("stats/", dashboard_stats, name="admin-stats"),
]