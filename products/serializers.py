from rest_framework import serializers
from .models import Product, Category, ProductImage
from django.utils.text import slugify
from django.conf import settings


class ProductImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductImage
        fields = ['id', 'product', 'image', 'alt', 'order']

    def to_representation(self, instance):
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
    category = serializers.PrimaryKeyRelatedField(queryset=Category.objects.all())
    images = ProductImageSerializer(many=True, read_only=True)
    category_obj = serializers.SerializerMethodField()  # ✅ Add method field

    class Meta:
        model = Product
        fields = (
            "id",
            "title",
            "slug",
            "description",
            "category",
            "category_obj",     # ✅ Make sure it’s here
            "is_active",
            "sales_count",
            "price",
            "discounted_price", # ✅ Include this if you’ve added it to the model
            "cost",             # ✅ Include cost if added
            "stock",
            "attributes",
            "trending",
            "images",
        )
        read_only_fields = ("slug", "sales_count")

    def get_category_obj(self, obj):
        """Return both subcategory and main category info."""
        cat = obj.category
        if not cat:
            return None
        return {
            "id": cat.id,
            "name": cat.name,
            "parent": cat.parent.id if cat.parent else None,
            "parent_name": cat.parent.name if cat.parent else None,
        }

    def validate(self, attrs):
        if attrs.get("is_active") and attrs.get("stock", 0) <= 0:
            raise serializers.ValidationError("Cannot activate a product with zero stock.")
        return attrs

    def create(self, validated_data):
        if not validated_data.get("slug"):
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