from django.contrib import admin
from .models import Order, OrderItem


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ["unit_price", "subtotal"]

    def subtotal(self, obj):
        return obj.subtotal
    subtotal.short_description = "Subtotal"


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ["id", "session_key", "user", "status", "total", "created_at"]
    list_filter = ["status", "created_at"]
    search_fields = ["user__username", "user__email", "id"]
    inlines = [OrderItemInline]
    readonly_fields = ["total", "created_at"]

    fieldsets = (
        ("Order Info", {
            "fields": ("user", "status", "total", "created_at")
        }),
        ("Shipping", {
            "fields": ("shipping_address",),
        }),
    )


@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = ["id", "order", "product", "quantity", "unit_price", "subtotal"]
    list_filter = ["order__status"]
    search_fields = ["product__title", "order__user__username"]

    def subtotal(self, obj):
        return obj.subtotal
    subtotal.short_description = "Subtotal"
