# orders/serializers.py
from rest_framework import serializers
from django.db import transaction
from .models import Order, OrderItem
from products.models import Product
from products.serializers import ProductSerializer
from decimal import Decimal


class OrderItemCreateSerializer(serializers.Serializer):
    product_id = serializers.IntegerField()
    quantity = serializers.IntegerField(min_value=1)


class OrderCreateSerializer(serializers.Serializer):
    items = OrderItemCreateSerializer(many=True)
    shipping_address = serializers.JSONField(required=False)
    phone_number = serializers.CharField(required=False, allow_blank=True, allow_null=True)

    def validate(self, data):
        for item in data["items"]:
            try:
                product = Product.objects.get(pk=item["product_id"])
            except Product.DoesNotExist:
                raise serializers.ValidationError(f"Product with ID {item['product_id']} does not exist.")
            if product.stock < item["quantity"]:
                raise serializers.ValidationError(f"Not enough stock for {product.title}.")
        return data

    def create(self, validated_data):
        items = validated_data.pop("items")
        user = self.context["request"].user if self.context["request"].user.is_authenticated else None

        with transaction.atomic():
            order = Order.objects.create(user=user, status=Order.Status.PENDING, **validated_data)
            total = Decimal("0.00")
            for it in items:
                product = Product.objects.select_for_update().get(pk=it["product_id"])
                if product.stock < it["quantity"]:
                    raise serializers.ValidationError(f"Not enough stock for {product.title}.")
                unit_price = product.get_effective_price() if product.get_effective_price() is not None else product.price
                OrderItem.objects.create(
                    order=order,
                    product=product,
                    quantity=it["quantity"],
                    unit_price=unit_price
                )
                product.stock -= it["quantity"]
                product.sales_count = (product.sales_count or 0) + it["quantity"]
                product.save()
                total += unit_price * it["quantity"]
            order.total = total
            order.save()
            return order


class OrderItemSerializer(serializers.ModelSerializer):
    product = ProductSerializer(read_only=True)

    class Meta:
        model = OrderItem
        fields = ["id", "product", "quantity", "unit_price", "subtotal"]
        read_only_fields = ["unit_price", "subtotal"]


class OrderDetailSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)

    class Meta:
        model = Order
        fields = ["id", "status", "total","phone_number", "shipping_address", "created_at", "items"]


class CartItemSerializer(serializers.ModelSerializer):
    product = ProductSerializer(read_only=True)
    product_id = serializers.PrimaryKeyRelatedField(
        queryset=Product.objects.all(),
        source="product",
        write_only=True
    )
    quantity = serializers.IntegerField(min_value=1)

    class Meta:
        model = OrderItem
        fields = ["id", "product", "product_id", "quantity", "unit_price", "subtotal"]
        read_only_fields = ["unit_price", "subtotal", "product"]


class CartSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)

    class Meta:
        model = Order
        fields = ["id", "items", "total", "status"]
