from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAdminUser
from django.db.models import Sum, Count, F
from django.db.models.functions import TruncDate, TruncMonth
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta
from analytics.models import Visitor
from rest_framework_simplejwt.authentication import JWTAuthentication

from orders.models import Order, OrderItem
from products.models import Product

User = get_user_model()


class AnalyticsViewSet(viewsets.ViewSet):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAdminUser]

    # ------------------------------------------------------------
    # Helper: timeframe range
    # ------------------------------------------------------------
    def get_date_range(self, request):
        r = request.query_params.get("range", "30")

        if r == "all":
            return None

        try:
            days = int(r)
        except ValueError:
            days = 30

        return timezone.now() - timedelta(days=days)

    # ------------------------------------------------------------
    # FILTERED Dashboard Stats
    # ------------------------------------------------------------
    @action(detail=False, methods=["get"])
    def stats(self, request):
        cutoff = self.get_date_range(request)

        orders = Order.objects.filter(status=Order.Status.PAID)
        if cutoff:
            orders = orders.filter(created_at__gte=cutoff)

        total_sales = orders.aggregate(total=Sum("total"))["total"] or 0
        total_orders = orders.count()

        # Users registered within period
        if cutoff:
            total_users = User.objects.filter(date_joined__gte=cutoff).count()
        else:
            total_users = User.objects.count()

        # Top product (filtered)
        top_product = (
            OrderItem.objects.filter(order__in=orders)
            .values("product_id", "product__title")
            .annotate(sales_count=Sum("quantity"))
            .order_by("-sales_count")
            .first()
        )

        return Response({
            "total_sales": total_sales,
            "total_orders": total_orders,
            "total_users": total_users,
            "top_product": {
                "id": top_product["product_id"],
                "title": top_product["product__title"],
                "sales_count": top_product["sales_count"]
            } if top_product else None,
        })

    # ------------------------------------------------------------
    # FILTERED Monthly Sales
    # ------------------------------------------------------------
    @action(detail=False, methods=["get"])
    def monthly_sales(self, request):
        cutoff = self.get_date_range(request)

        qs = Order.objects.filter(status=Order.Status.PAID)

        if cutoff:
            qs = qs.filter(created_at__gte=cutoff)

        monthly = (
            qs.annotate(month=TruncMonth("created_at"))
            .values("month")
            .annotate(total=Sum("total"))
            .order_by("month")
        )

        return Response(list(monthly))

    # ------------------------------------------------------------
    # FILTERED Sales Over Time (Cumulative)
    # ------------------------------------------------------------
    @action(detail=False, methods=["get"])
    def sales_over_time(self, request):
        cutoff = self.get_date_range(request)

        qs = Order.objects.filter(status=Order.Status.PAID)
        if cutoff:
            qs = qs.filter(created_at__gte=cutoff)

        qs = (
            qs.annotate(date=TruncDate("created_at"))
            .values("date")
            .annotate(total=Sum("total"))
            .order_by("date")
        )

        cumulative = 0
        data = []

        for row in qs:
            cumulative += float(row["total"])
            data.append({
                "date": row["date"],
                "cumulative_total": cumulative,
            })

        return Response(data)

    # ------------------------------------------------------------
    # FILTERED Profit Over Time (Cumulative + grouped by day)
    # ------------------------------------------------------------
    @action(detail=False, methods=["get"])
    def profit_over_time(self, request):
        cutoff = self.get_date_range(request)

        orders = Order.objects.filter(status=Order.Status.PAID)
        if cutoff:
            orders = orders.filter(created_at__gte=cutoff)

        # Group by date
        daily = {}

        for order in orders:
            d = order.created_at.date()

            items = OrderItem.objects.filter(order=order).select_related("product")
            cost = sum(
                (item.product.cost or 0) * item.quantity
                for item in items
            )

            profit = float(order.total) - float(cost)

            daily.setdefault(d, 0)
            daily[d] += profit

        # Build cumulative list
        cumulative = 0
        output = []

        for d in sorted(daily.keys()):
            cumulative += daily[d]
            output.append({
                "date": d,
                "profit": daily[d],
                "cumulative_profit": cumulative,
            })

        return Response(output)

    # ------------------------------------------------------------
    # FILTERED Order Status Summary
    # ------------------------------------------------------------
    @action(detail=False, methods=["get"])
    def order_status_summary(self, request):
        cutoff = self.get_date_range(request)

        qs = Order.objects.all()
        if cutoff:
            qs = qs.filter(created_at__gte=cutoff)

        data = {
            key: qs.filter(status=key).count()
            for key, _ in Order.Status.choices
        }

        return Response(data)

    # ------------------------------------------------------------
    # FILTERED Top Products by Category
    # ------------------------------------------------------------
    @action(detail=False, methods=["get"])
    def top_products_by_category(self, request):
        cutoff = self.get_date_range(request)
        category_param = request.query_params.get("category")

        items = OrderItem.objects.filter(order__status=Order.Status.PAID)

        if cutoff:
            items = items.filter(order__created_at__gte=cutoff)

        if category_param:
            ids = [int(x) for x in category_param.split(",") if x.isdigit()]
            items = items.filter(product__category_id__in=ids)

        products = (
            items.values("product_id", "product__title")
            .annotate(sales_count=Sum("quantity"))
            .order_by("-sales_count")[:10]
        )

        formatted = [
            {
                "id": p["product_id"],
                "title": p["product__title"],
                "sales_count": p["sales_count"],
            }
            for p in products
        ]

        return Response(formatted)

    # ------------------------------------------------------------
    # FILTERED Profit Summary
    # ------------------------------------------------------------
    @action(detail=False, methods=["get"])
    def profit(self, request):
        cutoff = self.get_date_range(request)

        paid = Order.objects.filter(status=Order.Status.PAID)
        if cutoff:
            paid = paid.filter(created_at__gte=cutoff)

        revenue = paid.aggregate(total=Sum("total"))["total"] or 0

        items = (
            OrderItem.objects.filter(order__in=paid)
            .select_related("product")
        )

        total_cost = sum(
            (item.product.cost or 0) * item.quantity
            for item in items
        )

        profit = revenue - total_cost

        return Response({
            "revenue": revenue,
            "cost": total_cost,
            "profit": profit,
        })

    # ------------------------------------------------------------
    # Visitors
    # ------------------------------------------------------------
    @action(detail=False, methods=["get"])
    def visitors(self, request):
        now = timezone.now()
        since_day = now - timedelta(days=1)
        since_month = now - timedelta(days=30)

        daily = Visitor.objects.filter(visited_at__gte=since_day).count()
        monthly = Visitor.objects.filter(visited_at__gte=since_month).count()

        return Response({"daily": daily, "monthly": monthly})
