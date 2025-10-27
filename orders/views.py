from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, IsAuthenticatedOrReadOnly
from .models import Order, OrderItem
from .serializers import (
    OrderCreateSerializer,
    OrderDetailSerializer,
    CartSerializer,
    CartItemSerializer,
)
from products.models import Product

from django.shortcuts import get_object_or_404
from rest_framework.permissions import AllowAny




# -----------------------------------------------------------------------------
# 🧾 ORDER VIEWSET
# -----------------------------------------------------------------------------
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


# -----------------------------------------------------------------------------
# 🛒 CART VIEWSET
# -----------------------------------------------------------------------------

class CartViewSet(viewsets.ViewSet):
    permission_classes = [AllowAny]

    def _get_cart(self, request, create_if_missing=True):
        """
        Get (or create) a cart for either logged-in user or guest session.
        Only creates if create_if_missing=True.
        """
        user = request.user if request.user.is_authenticated else None

        if not request.session.session_key:
            request.session.save()
        session_key = request.session.session_key

        # Common lookup filter
        lookup = {"status": Order.Status.PENDING}
        if user:
            lookup["user"] = user
        else:
            lookup["session_key"] = session_key

        try:
            return Order.objects.get(**lookup)
        except Order.DoesNotExist:
            if create_if_missing:
                return Order.objects.create(**lookup)
            return None


    def list(self, request):
        """View current cart contents"""
        cart = self._get_cart(request, create_if_missing=False)
        if not cart:
            return Response({"detail": "Cart is empty."}, status=200)
        serializer = CartSerializer(cart)
        return Response(serializer.data)


    @action(detail=False, methods=["post"])
    def add_item(self, request):
        """Add or update an item in the cart"""
        cart = self._get_cart(request)
        serializer = CartItemSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        product = serializer.validated_data["product"]
        quantity = serializer.validated_data["quantity"]

        # Only create or update cart item — no stock/sales logic here
        item, created = OrderItem.objects.get_or_create(
            order=cart,
            product=product,
            defaults={"quantity": quantity, "unit_price": product.price},
        )

        if not created:
            item.quantity += quantity
            item.save(update_fields=["quantity"])

        cart.recalculate_total()
        return Response(CartSerializer(cart).data, status=status.HTTP_200_OK)



    @action(detail=False, methods=["post"], url_path="remove_item")
    def remove_item(self, request):
        """Remove an item from the cart"""
        cart = self._get_cart(request, create_if_missing=True)
        item_id = request.data.get("item_id")

        try:
            item = cart.items.get(id=item_id)  # ✅ fixed
            item.delete()
            cart.recalculate_total()
            return Response(CartSerializer(cart).data)
        except OrderItem.DoesNotExist:
            return Response({"error": "Item not in cart"}, status=404)


    @action(detail=False, methods=["post"])
    def decrease_item(self, request):
        """Decrease quantity of an item"""
        cart = self._get_cart(request, create_if_missing=True)
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

    @action(detail=False, methods=["post"])
    def increase_item(self, request):
        """Increase quantity or add new item"""
        cart = self._get_cart(request, create_if_missing=True)
        product_id = request.data.get("product_id")

        product = get_object_or_404(Product, id=product_id)
        item, created = OrderItem.objects.get_or_create(
            order=cart,
            product=product,
            defaults={"quantity": 1, "unit_price": product.price}
        )
        if not created:
            item.quantity += 1
            item.save(update_fields=["quantity"])

        cart.recalculate_total()
        return Response(CartSerializer(cart).data)


    # -------------------------------------------------------------------------
    # 💳 CHECKOUT
    # -------------------------------------------------------------------------
    @action(detail=False, methods=["post"])
    def checkout(self, request):
        """Checkout and mark as paid"""
        # Always use the same helper to get the cart
        cart = self._get_cart(request, create_if_missing=True)

        if not cart.items.exists():
            return Response({"detail": "Your cart is empty."}, status=400)

        shipping_address = request.data.get("shipping_address")
        if shipping_address:
            cart.shipping_address = shipping_address
            cart.save(update_fields=["shipping_address"])

        try:
            cart.process_payment()
        except ValueError as e:
            return Response({"detail": str(e)}, status=400)

        serializer = OrderDetailSerializer(cart)
        return Response(
            {"detail": f"Order #{cart.id} checked out successfully!", "order": serializer.data},
            status=200,
        )


