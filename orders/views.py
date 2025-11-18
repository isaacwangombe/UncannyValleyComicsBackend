from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticatedOrReadOnly
from rest_framework_simplejwt.authentication import JWTAuthentication
from django.shortcuts import get_object_or_404
from decimal import Decimal

from .models import Order, OrderItem
from .serializers import (
    OrderCreateSerializer,
    OrderDetailSerializer,
    CartSerializer,
    CartItemSerializer,
)
from products.models import Product


# ============================================================
#  ORDER VIEWSET (kept from your original file)
# ============================================================
class OrderViewSet(viewsets.ModelViewSet):
    queryset = Order.objects.all().select_related("user").prefetch_related("items__product")
    serializer_class = OrderCreateSerializer

    def get_serializer_class(self):
        if self.action in ["list", "retrieve"]:
            return OrderDetailSerializer
        return OrderCreateSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        order = serializer.save()
        response_serializer = OrderDetailSerializer(order)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def pay(self, request, pk=None):
        order = self.get_object()
        try:
            order.process_payment()
            return Response({"detail": f"Order #{order.id} marked as paid."})
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        order = self.get_object()
        try:
            order.cancel_order()
            return Response({"detail": f"Order #{order.id} cancelled."})
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["post"])
    def refund(self, request, pk=None):
        order = self.get_object()
        try:
            order.refund_order()
            return Response({"detail": f"Order #{order.id} refunded."})
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)


# ============================================================
#  CART VIEWSET (your fixed version)
# ============================================================
class CartViewSet(viewsets.ViewSet):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticatedOrReadOnly]

    # ---------------------------------------------------------
    # Ensure session exists
    # ---------------------------------------------------------
    def _ensure_session(self, request):
        if not request.session.session_key:
            request.session.save()
        return request.session.session_key

    # ---------------------------------------------------------
    # Retrieve or create cart
    # ---------------------------------------------------------
    def _get_cart(self, request, create_if_missing=True):
        user = request.user if request.user.is_authenticated else None
        session_key = self._ensure_session(request)

        lookup = {"status": Order.Status.PENDING}

        if user:
            lookup["user"] = user
        else:
            lookup["session_key"] = session_key

        try:
            cart = Order.objects.get(**lookup)

            # upgrade guest cart → user cart
            if user and not cart.user:
                cart.user = user
                cart.session_key = session_key
                cart.save(update_fields=["user", "session_key"])

            return cart

        except Order.DoesNotExist:
            if not create_if_missing:
                return None

            if user:
                return Order.objects.create(user=user, session_key=session_key)
            return Order.objects.create(session_key=session_key)

    # ---------------------------------------------------------
    # GET /cart/
    # ---------------------------------------------------------
    def list(self, request):
        cart = self._get_cart(request, create_if_missing=False)
        if not cart:
            return Response({"detail": "Cart is empty."}, status=200)
        return Response(CartSerializer(cart).data)

    # ---------------------------------------------------------
    # POST /cart/add_item/
    # ---------------------------------------------------------
    @action(detail=False, methods=["post"])
    def add_item(self, request):
        cart = self._get_cart(request)
        serializer = CartItemSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        product = serializer.validated_data["product"]
        quantity = serializer.validated_data["quantity"]

        eff_price = product.get_effective_price() or product.price

        item, created = OrderItem.objects.get_or_create(
            order=cart,
            product=product,
            defaults={"quantity": quantity, "unit_price": eff_price},
        )

        if not created:
            item.quantity += quantity
            item.save(update_fields=["quantity"])

        cart.recalculate_total()
        return Response(CartSerializer(cart).data)

    # ---------------------------------------------------------
    # POST /cart/remove_item/
    # ---------------------------------------------------------
    @action(detail=False, methods=["post"], url_path="remove_item")
    def remove_item(self, request):
        cart = self._get_cart(request)
        item_id = request.data.get("item_id")

        try:
            item = cart.items.get(id=item_id)
            item.delete()
            cart.recalculate_total()
        except OrderItem.DoesNotExist:
            return Response({"error": "Item not in cart"}, status=404)

        return Response(CartSerializer(cart).data)

    # ---------------------------------------------------------
    # POST /cart/decrease_item/
    # ---------------------------------------------------------
    @action(detail=False, methods=["post"])
    def decrease_item(self, request):
        cart = self._get_cart(request)
        product_id = request.data.get("product_id")

        try:
            item = cart.items.get(product_id=product_id)
        except OrderItem.DoesNotExist:
            return Response({"detail": "Item not found in cart."}, status=404)

        item.quantity -= 1
        if item.quantity <= 0:
            item.delete()
        else:
            item.save(update_fields=["quantity"])

        cart.recalculate_total()
        return Response(CartSerializer(cart).data)

    # ---------------------------------------------------------
    # POST /cart/increase_item/
    # ---------------------------------------------------------
    @action(detail=False, methods=["post"])
    def increase_item(self, request):
        cart = self._get_cart(request)
        product_id = request.data.get("product_id")

        product = get_object_or_404(Product, id=product_id)
        eff_price = product.get_effective_price() or product.price

        item, created = OrderItem.objects.get_or_create(
            order=cart,
            product=product,
            defaults={"quantity": 1, "unit_price": eff_price},
        )

        if not created:
            item.quantity += 1
            item.save(update_fields=["quantity"])

        cart.recalculate_total()
        return Response(CartSerializer(cart).data)

    # ---------------------------------------------------------
    # POST /cart/checkout/
    # ---------------------------------------------------------
    @action(detail=False, methods=["post"])
    def checkout(self, request):
        cart = self._get_cart(request)

        if not cart.items.exists():
            return Response({"detail": "Your cart is empty."}, status=400)

        shipping_address = request.data.get("shipping_address", {}) or {}
        phone_number = request.data.get("phone_number")

        if request.user.is_authenticated:
            cart.user = request.user

        cart.shipping_address = shipping_address
        if phone_number:
            cart.phone_number = phone_number

        cart.save(update_fields=["shipping_address", "phone_number", "user"])

        try:
            cart.process_payment()
        except ValueError as e:
            return Response({"detail": str(e)}, status=400)

        return Response({"detail": "Checkout successful!"}, status=200)
