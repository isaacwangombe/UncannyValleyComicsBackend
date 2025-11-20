# orders/views.py
from rest_framework import viewsets, status
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticatedOrReadOnly, IsAdminUser, AllowAny
from rest_framework_simplejwt.authentication import JWTAuthentication

from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.conf import settings
from django.core.mail import EmailMessage

from .models import Order, OrderItem, EventTicket
from .serializers import (
    OrderCreateSerializer,
    OrderDetailSerializer,
    CartSerializer,
    CartItemSerializer,
)

from products.models import Product, EventExtension
from .utils.qr import generate_qr_base64


class OrderViewSet(viewsets.ModelViewSet):
    queryset = Order.objects.all().select_related("user").prefetch_related("items__product")
    serializer_class = OrderCreateSerializer
    authentication_classes = [JWTAuthentication]

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
            return Response({"detail": str(e)}, status=400)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        order = self.get_object()
        try:
            order.cancel_order()
            return Response({"detail": f"Order #{order.id} cancelled."})
        except ValueError as e:
            return Response({"detail": str(e)}, status=400)

    @action(detail=True, methods=["post"])
    def refund(self, request, pk=None):
        order = self.get_object()
        try:
            order.refund_order()
            return Response({"detail": f"Order #{order.id} refunded."})
        except ValueError as e:
            return Response({"detail": str(e)}, status=400)


class CartViewSet(viewsets.ViewSet):
    authentication_classes = [JWTAuthentication]
    permission_classes = [AllowAny]

    def _ensure_session(self, request):
        if not request.session.session_key:
            request.session.save()
        return request.session.session_key

    def _get_cart(self, request, create_if_missing=True):
        user = request.user if request.user.is_authenticated else None
        session_key = self._ensure_session(request)

        if user:
            try:
                user_cart = Order.objects.get(user=user, status=Order.Status.PENDING)
            except Order.DoesNotExist:
                user_cart = None

            try:
                session_cart = Order.objects.get(session_key=session_key, status=Order.Status.PENDING)
            except Order.DoesNotExist:
                session_cart = None

            if user_cart and session_cart and user_cart.id != session_cart.id:
                for item in session_cart.items.all():
                    existing = user_cart.items.filter(product=item.product).first()
                    if existing:
                        existing.quantity += item.quantity
                        existing.save()
                    else:
                        item.order = user_cart
                        item.save()
                session_cart.delete()

            if not user_cart:
                user_cart = Order.objects.create(user=user, session_key=session_key)

            user_cart.session_key = session_key
            user_cart.user = user
            user_cart.save(update_fields=["session_key", "user"])
            return user_cart

        try:
            return Order.objects.get(session_key=session_key, status=Order.Status.PENDING)
        except Order.DoesNotExist:
            if create_if_missing:
                return Order.objects.create(session_key=session_key)
            return None

    def list(self, request):
        cart = self._get_cart(request, create_if_missing=False)
        if not cart:
            return Response({"items": [], "total": 0}, status=200)
        return Response(CartSerializer(cart).data)

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

    @action(detail=False, methods=["post"])
    def decrease_item(self, request):
        cart = self._get_cart(request)
        product_id = request.data.get("product_id")
        try:
            item = cart.items.get(product_id=product_id)
        except OrderItem.DoesNotExist:
            return Response({"detail": "Item not found"}, status=404)

        item.quantity -= 1
        if item.quantity <= 0:
            item.delete()
        else:
            item.save(update_fields=["quantity"])

        cart.recalculate_total()
        return Response(CartSerializer(cart).data)

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

        # Checkout email ALWAYS takes priority over logged-in user email
        recipient_email = shipping_address.get("email") or (
            cart.user.email if cart.user else None
        )

        if not recipient_email:
            return Response({"detail": "No email available"}, status=400)


        # send a single email containing all tickets (attachments)
        attachments = []
        for item in cart.items.all():
            # item may have many tickets (if quantity > 1)
            for ticket in item.tickets.all():
                # attach each ticket PNG
                qr_url = f"{settings.SITE_URL.rstrip('/')}/api/events/verify/{ticket.code}/"
                # generate base64 and convert to bytes
                b64 = generate_qr_base64(qr_url)
                img_bytes = b64.encode("utf-8")
                # we want raw PNG bytes — generate_qr_base64 returns base64 of PNG.
                # convert base64 -> bytes:
                import base64 as _b64
                png = _b64.b64decode(b64)
                attachments.append((f"ticket-{ticket.code}.png", png, "image/png"))

        # Compose single email with HTML listing all tickets and attach images
        html_lines = ["<h3>Your Tickets</h3>", "<ul>"]
        for item in cart.items.all():
            if item.tickets.exists():
                html_lines.append(f"<li>{item.product.title} × {item.quantity}</li>")
        html_lines.append("</ul>")
        html_body = "\n".join(html_lines)

        email = EmailMessage(
            subject=f"Your Tickets from {settings.SITE_URL}",
            body=html_body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[recipient_email],
        )
        email.content_subtype = "html"
        for name, data, mime in attachments:
            email.attach(name, data, mime)
        email.send(fail_silently=False)

        return Response({
            "detail": "Checkout successful!",
            "order_id": cart.id,
        }, status=200)


@api_view(["GET"])
@permission_classes([IsAdminUser])
def verify_event_ticket(request, code):
    try:
        ticket = EventTicket.objects.get(code=code)
    except EventTicket.DoesNotExist:
        return Response({"valid": False, "error": "Invalid ticket"}, status=404)

    if ticket.used:
        return Response({
            "valid": False,
            "error": "Ticket already used",
            "used_at": ticket.used_at,
        })

    ticket.used = True
    ticket.used_at = timezone.now()
    ticket.save(update_fields=["used", "used_at"])

    return Response({
        "valid": True,
        "event": ticket.order_item.product.title,
        "used_at": ticket.used_at,
    })


@api_view(["GET"])
@permission_classes([IsAdminUser])
def scan_ticket(request, code):
    """
    Admin-only ticket scanning & verification endpoint.
    """
    try:
        ticket = EventTicket.objects.select_related(
            "order_item__product"
        ).get(code=code)
    except EventTicket.DoesNotExist:
        return Response({"valid": False, "error": "Invalid ticket"}, status=404)

    data = {
        "valid": not ticket.used,
        "used": ticket.used,
        "event": ticket.order_item.product.title,
        "ticket_id": ticket.code,
        "used_at": ticket.used_at,
    }

    # If not used yet → mark as used
    if not ticket.used:
        ticket.used = True
        ticket.used_at = timezone.now()
        ticket.save(update_fields=["used", "used_at"])

    return Response(data, status=200)
