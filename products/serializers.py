from rest_framework import serializers
from .models import Product, Category, ProductImage
from django.utils.text import slugify
from django.conf import settings


class ProductImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductImage
        fields = ['id', 'product', 'image', 'alt', 'order']  # include 'product' and 'image'
        extra_kwargs = {
            'product': {'required': True, 'allow_null': False},
            'image': {'required': True, 'allow_null': False},
        }

    def to_representation(self, instance):
        """Return a full Cloudinary or absolute local URL."""
        data = super().to_representation(instance)
        image = instance.image

        if image:
            url = str(image)
            if url.startswith("http"):
                data["image"] = url
            elif url.startswith("image/upload"):
                data["image"] = f"https://res.cloudinary.com/{settings.CLOUDINARY_CLOUD_NAME}/{url}"
            elif hasattr(image, "url"):
                request = self.context.get("request")
                data["image"] = request.build_absolute_uri(image.url) if request else image.url
            else:
                data["image"] = None
        else:
            data["image"] = None

        return data

class ProductSerializer(serializers.ModelSerializer):
    # make category writable by using its primary key
    category = serializers.PrimaryKeyRelatedField(queryset=Category.objects.all())
    images = ProductImageSerializer(many=True, read_only=True)

    class Meta:
        model = Product
        fields = (
            "id",
            "title",
            "slug",
            "description",
            "category",
            "is_active",
            "sales_count",
            "price",
            "stock",
            "attributes",
            "trending",
            "images",
        )
        read_only_fields = ("slug", "sales_count")

    def validate(self, attrs):
        if attrs.get("is_active") and attrs.get("stock", 0) <= 0:
            raise serializers.ValidationError(
                "Cannot activate a product with zero stock."
            )
        return attrs
    
    def create(self, validated_data):
        # auto-generate slug if missing
        if not validated_data.get("slug"):
            from django.utils.text import slugify
            validated_data["slug"] = slugify(validated_data["title"])
        return super().create(validated_data)


class CategorySerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = Category
        fields = "__all__"
        read_only_fields = ["slug"]

    def get_image_url(self, obj):
        """Return full Cloudinary image URL if available."""
        if obj.image:
            try:
                return obj.image.url
            except Exception:
                return None
        return None

    def create(self, validated_data):
        # ✅ Auto-generate slug
        validated_data["slug"] = slugify(validated_data["name"])
        return super().create(validated_data)

    def update(self, instance, validated_data):
        # ✅ Update slug if name changes
        if "name" in validated_data:
            validated_data["slug"] = slugify(validated_data["name"])
        return super().update(instance, validated_data)