# orders/models.py
from django.db import models, transaction
from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver
from decimal import Decimal
import uuid
from django.core.mail import send_mail

from products.models import Product
from .utils.qr import generate_qr_base64  # orders/utils/qr.py

class Order(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PAID = "paid", "Paid"
        SHIPPED = "shipped", "Shipped"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"
        REFUNDED = "refunded", "Refunded"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    session_key = models.CharField(max_length=40, blank=True, null=True, db_index=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    total = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    shipping_address = models.JSONField(blank=True, null=True)
    phone_number = models.CharField(max_length=20, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "status"],
                condition=models.Q(status="pending"),
                name="unique_pending_order_per_user",
            ),
            models.UniqueConstraint(
                fields=["session_key", "status"],
                condition=models.Q(status="pending"),
                name="unique_pending_order_per_session",
            ),
        ]

    def __str__(self):
        who = self.user or (f"Guest:{self.session_key[:8]}" if self.session_key else "Guest")
        return f"Order #{self.pk} — {who}"

    def recalculate_total(self):
        self.total = sum(item.subtotal for item in self.items.all())
        self.save(update_fields=["total"])

    @transaction.atomic
    def process_payment(self):
        """
        Mark order as PAID and adjust stock & sales.
        Also create EventTicket objects for event products (one ticket per unit quantity).
        This method is idempotent (if already PAID, does nothing).
        """
        if self.status == self.Status.PAID:
            return

        for item in self.items.select_related("product"):
            product = item.product

            if product.stock < item.quantity:
                raise ValueError(f"Not enough stock for {product.title}")

            # adjust stock & sales
            product.stock -= item.quantity
            product.sales_count = (product.sales_count or 0) + item.quantity
            product.save(update_fields=["stock", "sales_count"])

            # If product has event_data (EventExtension) -> create tickets (one per unit)
            # We create separate EventTicket rows so each QR is single-use.
            try:
                # check for presence of event extension
                _ = getattr(product, "event_data", None)
                is_event = _ is not None
            except Exception:
                is_event = False

            if is_event:
                # create N tickets (N = quantity)
                for _i in range(int(item.quantity or 1)):
                    EventTicket.objects.create(order_item=item)

        self.status = self.Status.PAID
        self.save(update_fields=["status"])


    # --- Cart helpers ---
    @classmethod
    def get_or_create_cart(cls, user=None, session_key=None):
        """Return (or create) a cart for either user or guest session."""
        if user and getattr(user, "is_authenticated", False):
            order, _ = cls.objects.get_or_create(user=user, status=cls.Status.PENDING)
        elif session_key:
            order, _ = cls.objects.get_or_create(session_key=session_key, status=cls.Status.PENDING)
        else:
            raise ValueError("Cart requires a user or session key")
        return order


class OrderItem(models.Model):
    order = models.ForeignKey(Order, related_name="items", on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    quantity = models.PositiveIntegerField()
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        return f"{self.product.title} × {self.quantity}"

    @property
    def subtotal(self):
        if self.unit_price is None or self.quantity is None:
            return Decimal("0.00")
        return self.unit_price * self.quantity

    def save(self, *args, **kwargs):
        # set unit_price to effective product price if missing
        if (self.unit_price is None or self.unit_price == 0) and self.product:
            eff = self.product.get_effective_price()
            self.unit_price = eff if eff is not None else self.product.price
        super().save(*args, **kwargs)


@receiver(post_save, sender=OrderItem)
def recalc_total_on_item_add(sender, instance, created, **kwargs):
    if created:
        instance.order.recalculate_total()


class EventTicket(models.Model):
    """
    Many tickets can map to one OrderItem (one ticket per seat/quantity).
    Each ticket has a unique code (UUID) and can be marked used once.
    """
    order_item = models.ForeignKey(OrderItem, related_name="tickets", on_delete=models.CASCADE)
    code = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    used = models.BooleanField(default=False)
    used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def qr_base64(self):
        # form a validate URL (use SITE_URL from settings)
        validate_url =  f"{settings.SITE_URL}/scan/{self.code}/"
        return generate_qr_base64(validate_url)

    def send_ticket_email(self, recipient_email=None):
        """
        Convenience: send single-ticket email. The view sends bulk emails after checkout.
        """
        order = self.order_item.order
        product = self.order_item.product
        email = (
            order.shipping_address.get("email")
            or (order.user.email if order.user else None)
        )
        if not email:
            return

        # prefer EventExtension if present
        event_info = getattr(product, "event_data", None)
        start = getattr(event_info, "start", None) if event_info else getattr(product, "event_start", None)
        end = getattr(event_info, "end", None) if event_info else getattr(product, "event_end", None)
        location = getattr(event_info, "location", None) if event_info else getattr(product, "event_location", None)

        message = (
            f"Your ticket for {product.title}\n\n"
            f"Location: {location}\n"
            f"Starts: {start}\n"
            f"Ends: {end}\n\n"
            f"Show this QR code at entry."
        )

        html = f"""
        <h2>Your Ticket For {product.title}</h2>
        <p><strong>Location:</strong> {location}</p>
        <p><strong>Starts:</strong> {start}</p>
        <p><strong>Ends:</strong> {end}</p>
        <br>
        <p>Show this QR code at entry:</p>
        <img src="data:image/png;base64,{self.qr_base64}">
        """

        send_mail(
            subject=f"Your Ticket for {product.title}",
            message=message,
            html_message=html,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[email],
            fail_silently=False,
        )

    def __str__(self):
        return f"Ticket {self.code}"
