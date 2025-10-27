from django.db import models, transaction
from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver
from products.models import Product



class Order(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PAID = "paid", "Paid"
        SHIPPED = "shipped", "Shipped"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"
        REFUNDED = "refunded", "Refunded"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    session_key = models.CharField(max_length=40, blank=True, null=True, db_index=True)  # 👈 added
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    total = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    shipping_address = models.JSONField(blank=True, null=True)
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
        who = self.user or f"Guest:{self.session_key[:8]}" if self.session_key else "Guest"
        return f"Order #{self.pk} — {who}"
    

  # ✅ calculate total from items
    def recalculate_total(self):
        self.total = sum(item.subtotal for item in self.items.all())
        self.save(update_fields=["total"])


    # ✅ process payment safely
    @transaction.atomic
    def process_payment(self):
        """Mark order as PAID and adjust stock & sales."""
        if self.status == self.Status.PAID:
            return  # avoid double-processing

        for item in self.items.select_related("product"):
            product = item.product

            if product.stock < item.quantity:
                raise ValueError(f"Not enough stock for {product.title}")

            # update product stock & sales
            product.stock -= item.quantity
            product.sales_count = (product.sales_count or 0) + item.quantity
            product.save(update_fields=["stock", "sales_count"])

        self.status = self.Status.PAID
        self.save(update_fields=["status"])   

    # --- Cart helpers ---
    @classmethod
    def get_or_create_cart(cls, user=None, session_key=None):
        """Return (or create) a cart for either user or guest session."""
        if user and user.is_authenticated:
            order, _ = cls.objects.get_or_create(user=user, status=cls.Status.PENDING)
        elif session_key:
            order, _ = cls.objects.get_or_create(session_key=session_key, status=cls.Status.PENDING)
        else:
            raise ValueError("Cart requires a user or session key")
        return order

    def recalculate_total(self):
        self.total = sum(item.subtotal for item in self.items.all())
        self.save(update_fields=["total"])

    @transaction.atomic
    def process_payment(self):
        """Mark order as paid and adjust product stock & sales."""
        if self.status == self.Status.PAID:
            return
        for item in self.items.select_related("product"):
            product = item.product
            if product.stock < item.quantity:
                raise ValueError(f"Not enough stock for {product.title}")
            product.stock -= item.quantity
            product.sales_count += item.quantity
            product.save(update_fields=["stock", "sales_count"])
        self.status = self.Status.PAID
        self.save(update_fields=["status"])

    @transaction.atomic
    def cancel_order(self):
        """Cancel order and restore stock if it was paid."""
        if self.status not in [self.Status.PAID, self.Status.SHIPPED]:
            return
        for item in self.items.select_related("product"):
            product = item.product
            product.stock += item.quantity
            product.sales_count = max(product.sales_count - item.quantity, 0)
            product.save(update_fields=["stock", "sales_count"])
        self.status = self.Status.CANCELLED
        self.save(update_fields=["status"])

    @transaction.atomic
    def refund_order(self):
        """Refund order and restore stock."""
        if self.status != self.Status.PAID:
            return
        for item in self.items.select_related("product"):
            product = item.product
            product.stock += item.quantity
            product.sales_count = max(product.sales_count - item.quantity, 0)
            product.save(update_fields=["stock", "sales_count"])
        self.status = self.Status.REFUNDED
        self.save(update_fields=["status"])


class OrderItem(models.Model):
    order = models.ForeignKey(Order, related_name="items", on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    quantity = models.PositiveIntegerField()
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        return f"{self.product.title} × {self.quantity}"

    @property
    def subtotal(self):
        # ✅ Safe multiplication even if values are None
        if self.unit_price is None or self.quantity is None:
            return 0
        return self.unit_price * self.quantity
    
    def save(self, *args, **kwargs):
        if self.unit_price is None and self.product:
            self.unit_price = self.product.price
        super().save(*args, **kwargs)


# -----------------------------------------------------
# SIGNALS — Auto recalc order total when items added
# -----------------------------------------------------
@receiver(post_save, sender=OrderItem)
def recalc_total_on_item_add(sender, instance, created, **kwargs):
    if created:
        instance.order.recalculate_total()
