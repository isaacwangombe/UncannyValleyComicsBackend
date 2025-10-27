from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAdminUser
from django.db.models import Sum, Count
from django.db.models.functions import TruncDate, TruncMonth
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta
from analytics.models import Visitor
from django.http import JsonResponse


from orders.models import Order
from products.models import Product

User = get_user_model()


class AnalyticsViewSet(viewsets.ViewSet):
    """
    Provides admin analytics endpoints:
    - /api/admin/analytics/stats/
    - /api/admin/analytics/daily_sales/
    - /api/admin/analytics/monthly_sales/
    - /api/admin/analytics/sales_over_time/
    - /api/admin/analytics/new_users/
    - /api/admin/analytics/top_products/
    """

    permission_classes = [IsAdminUser]

    # -------------------------------------------------------------------------
    # 1️⃣ STATS OVERVIEW
    # -------------------------------------------------------------------------
    @action(detail=False, methods=["get"])
    def stats(self, request):
        """Get overall store metrics"""
        total_sales = (
            Order.objects.filter(status=Order.Status.PAID)
            .aggregate(total=Sum("total"))["total"]
            or 0
        )
        total_orders = Order.objects.filter(status=Order.Status.PAID).count()
        total_users = User.objects.count()
        top_product = Product.objects.order_by("-sales_count").first()

        return Response(
            {
                "total_sales": total_sales,
                "total_orders": total_orders,
                "total_users": total_users,
                "top_product": {
                    "id": top_product.id,
                    "title": top_product.title,
                    "sales_count": top_product.sales_count,
                }
                if top_product
                else None,
            }
        )

    # -------------------------------------------------------------------------
    # 2️⃣ DAILY SALES (for past 30 days)
    # -------------------------------------------------------------------------
    @action(detail=False, methods=["get"])
    def daily_sales(self, request):
        """Return daily revenue totals for the past 30 days"""
        since = timezone.now() - timedelta(days=30)
        sales = (
            Order.objects.filter(status=Order.Status.PAID, created_at__gte=since)
            .annotate(date=TruncDate("created_at"))
            .values("date")
            .annotate(total=Sum("total"))
            .order_by("date")
        )
        return Response(list(sales))

    # -------------------------------------------------------------------------
    # 3️⃣ MONTHLY SALES (for the past 12 months)
    # -------------------------------------------------------------------------
    @action(detail=False, methods=["get"])
    def monthly_sales(self, request):
        """Return monthly revenue totals for the last 12 months"""
        since = timezone.now() - timedelta(days=365)
        monthly = (
            Order.objects.filter(status=Order.Status.PAID, created_at__gte=since)
            .annotate(month=TruncMonth("created_at"))
            .values("month")
            .annotate(total=Sum("total"))
            .order_by("month")
        )
        return Response(list(monthly))

    # -------------------------------------------------------------------------
    # 4️⃣ SALES OVER TIME (CUMULATIVE)
    # -------------------------------------------------------------------------
    @action(detail=False, methods=["get"])
    def sales_over_time(self, request):
        """Return cumulative sales over time for charting growth"""
        since = timezone.now() - timedelta(days=180)
        daily = (
            Order.objects.filter(status=Order.Status.PAID, created_at__gte=since)
            .annotate(date=TruncDate("created_at"))
            .values("date")
            .annotate(total=Sum("total"))
            .order_by("date")
        )

        cumulative = []
        running_total = 0
        for day in daily:
            running_total += day["total"] or 0
            cumulative.append({
                "date": day["date"],
                "cumulative_total": running_total
            })

        return Response(cumulative)

    # -------------------------------------------------------------------------
    # 5️⃣ NEW USERS TREND
    # -------------------------------------------------------------------------
    @action(detail=False, methods=["get"])
    def new_users(self, request):
        """Return new registered users grouped by date"""
        users = (
            User.objects.annotate(date=TruncDate("date_joined"))
            .values("date")
            .annotate(count=Count("id"))
            .order_by("date")
        )
        return Response(list(users))

    # -------------------------------------------------------------------------
    # 6️⃣ TOP PRODUCTS
    # -------------------------------------------------------------------------
    @action(detail=False, methods=["get"])
    def top_products(self, request):
        """Return top 5 selling products"""
        products = (
            Product.objects.order_by("-sales_count")
            .values("id", "title", "sales_count", "price")[:5]
        )
        return Response(list(products))
    
    # -------------------------------------------------------------------------
    # 7️⃣ VISITOR STATS (DAILY / MONTHLY)
    # -------------------------------------------------------------------------
    @action(detail=False, methods=["get"])
    def visitors(self, request):
        """Return daily and monthly unique visitor counts"""
        now = timezone.now()
        since_day = now - timedelta(days=1)
        since_month = now - timedelta(days=30)

        daily = Visitor.objects.filter(visited_at__gte=since_day).count()
        monthly = Visitor.objects.filter(visited_at__gte=since_month).count()

        return Response({"daily": daily, "monthly": monthly})

