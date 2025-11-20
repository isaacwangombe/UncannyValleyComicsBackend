# products/admin.py
from django.contrib import admin
from .models import Category, Product, ProductImage, EventExtension

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "parent", "id")
    prepopulated_fields = {"slug": ("name",)}


class EventExtensionInline(admin.StackedInline):
    model = EventExtension
    extra = 0
    max_num = 1   # one event per product
    can_delete = True
    fields = ("start", "end", "location")  # capacity removed if you no longer use it


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 1


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "sku",
        "price",
        "discounted_price",
        "stock",
        "is_active",
        "sales_count",
        "category",
    )
    prepopulated_fields = {"slug": ("title",)}
    search_fields = ("title", "description")
    list_filter = ("is_active", "category")

    inlines = [EventExtensionInline, ProductImageInline]


@admin.register(ProductImage)
class ProductImageAdmin(admin.ModelAdmin):
    list_display = ("product", "image", "order")
