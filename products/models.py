# products/models.py
from django.db import models
import uuid
from django.utils.text import slugify
from django.core.validators import MinValueValidator
from cloudinary.models import CloudinaryField
from decimal import Decimal
from django.conf import settings

# Hard-coded category IDs (per your request)
UPCOMING_CATEGORY_ID = 10
PAST_CATEGORY_ID = 9


class Category(models.Model):
    name = models.CharField(max_length=120, unique=True)
    slug = models.SlugField(max_length=140, unique=True)
    parent = models.ForeignKey(
        "self", related_name="subcategories", on_delete=models.CASCADE, blank=True, null=True
    )
    image = CloudinaryField("image", folder="category_images", blank=True, null=True)

    class Meta:
        verbose_name_plural = "Categories"

    def __str__(self):
        return self.name


class Product(models.Model):
    title = models.CharField(max_length=250)
    slug = models.SlugField(max_length=260, unique=True)
    description = models.TextField(blank=True)
    category = models.ForeignKey(Category, related_name="products", on_delete=models.PROTECT)
    is_active = models.BooleanField(default=True)
    sales_count = models.PositiveIntegerField(default=0)

    # merged variant fields
    sku = models.CharField(max_length=80, blank=True, null=True)
    price = models.DecimalField(
        max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal("0.00"))]
    )
    cost = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
        blank=True,
        null=True,
        help_text="Cost price (optional)",
    )
    discounted_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
        blank=True,
        null=True,
        help_text="If set, this price is used instead of `price` for sales",
    )

    # stock acts as capacity/seats for events
    stock = models.IntegerField(default=0)
    attributes = models.JSONField(blank=True, null=True)
    trending = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title

    def get_effective_price(self):
        return self.discounted_price if self.discounted_price is not None else self.price

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title)
        # auto-deactivate when out of stock
        if self.stock <= 0:
            self.is_active = False
        else:
            self.is_active = True
        super().save(*args, **kwargs)


class ProductImage(models.Model):
    product = models.ForeignKey(Product, related_name="images", on_delete=models.CASCADE)
    image = CloudinaryField("image", folder="product_images/")
    alt = models.CharField(max_length=150, blank=True)
    order = models.PositiveSmallIntegerField(default=0)

    def __str__(self):
        return f"Image for {self.product.title}"

    def delete(self, *args, **kwargs):
        from cloudinary.uploader import destroy

        if self.image and hasattr(self.image, "public_id"):
            destroy(self.image.public_id)
        super().delete(*args, **kwargs)


class EventExtension(models.Model):
    """
    1:1 extension attached to Product for event-specific fields.
    NOTE: capacity removed — use Product.stock as capacity/seats.
    """
    product = models.OneToOneField(Product, related_name="event_data", on_delete=models.CASCADE)
    start = models.DateTimeField()
    end = models.DateTimeField(null=True, blank=True)
    location = models.CharField(max_length=250, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Event data for {self.product.title}"

