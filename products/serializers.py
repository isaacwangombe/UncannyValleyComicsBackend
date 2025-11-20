# products/serializers.py
from rest_framework import serializers
from .models import Product, Category, ProductImage, EventExtension, UPCOMING_CATEGORY_ID, PAST_CATEGORY_ID
from django.utils.text import slugify
from django.conf import settings
from django.utils import timezone


class ProductImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductImage
        fields = ["id", "product", "image", "alt", "order"]

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


class EventExtensionSerializer(serializers.ModelSerializer):
    start = serializers.DateTimeField()
    end = serializers.DateTimeField(required=False, allow_null=True)
    location = serializers.CharField(required=False, allow_blank=True)

    class Meta:
        model = EventExtension
        fields = ["start", "end", "location", "created_at"]
        read_only_fields = ["created_at"]


class ProductSerializer(serializers.ModelSerializer):
    category = serializers.PrimaryKeyRelatedField(queryset=Category.objects.all())
    images = ProductImageSerializer(many=True, read_only=True)
    category_obj = serializers.SerializerMethodField()
    # writable nested event_data
    event_data = EventExtensionSerializer(required=False, allow_null=True)

    class Meta:
        model = Product
        fields = (
            "id",
            "title",
            "slug",
            "description",
            "category",
            "category_obj",
            "is_active",
            "sales_count",
            "price",
            "discounted_price",
            "cost",
            "stock",
            "attributes",
            "trending",
            "images",
            "event_data",
        )
        read_only_fields = ("slug", "sales_count")

    def get_category_obj(self, obj):
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

    def _determine_event_category_id(self, event_data):
        """
        Rule A: if event.end < now -> Past (PAST_CATEGORY_ID)
                else -> Upcoming (UPCOMING_CATEGORY_ID)
        If end is None, fall back to start < now -> Past
        """
        now = timezone.now()
        try:
            end = event_data.get("end", None)
            start = event_data.get("start", None)
        except Exception:
            return UPCOMING_CATEGORY_ID

        if end:
            if end < now:
                return PAST_CATEGORY_ID
            return UPCOMING_CATEGORY_ID
        if start:
            if start < now:
                return PAST_CATEGORY_ID
            return UPCOMING_CATEGORY_ID
        return UPCOMING_CATEGORY_ID

    def create(self, validated_data):
        event_data = validated_data.pop("event_data", None)

        # auto-generate slug if not present
        if not validated_data.get("slug"):
            validated_data["slug"] = slugify(validated_data.get("title", ""))

        # If event_data provided, determine category id and override validated_data['category']
        if event_data:
            try:
                cat_id = self._determine_event_category_id(event_data)
                validated_data["category"] = Category.objects.get(pk=cat_id)
            except Category.DoesNotExist:
                # fallback to whatever category was supplied or raise
                pass

        product = super().create(validated_data)

        if event_data:
            # create event extension
            EventExtension.objects.create(product=product, **event_data)

        return product

    def update(self, instance, validated_data):
        event_data = validated_data.pop("event_data", None)

        # Generate slug if title changed
        if "title" in validated_data and not validated_data.get("slug"):
            validated_data["slug"] = slugify(validated_data["title"])

        # If event_data provided, set the appropriate category (upcoming/past)
        if event_data:
            try:
                cat_id = self._determine_event_category_id(event_data)
                validated_data["category"] = Category.objects.get(pk=cat_id)
            except Category.DoesNotExist:
                pass

        product = super().update(instance, validated_data)

        if event_data:
            # update existing EventExtension or create
            if hasattr(product, "event_data"):
                for k, v in event_data.items():
                    setattr(product.event_data, k, v)
                product.event_data.save()
            else:
                EventExtension.objects.create(product=product, **event_data)

        return product


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
        validated_data["slug"] = slugify(validated_data["name"])
        return super().create(validated_data)

    def update(self, instance, validated_data):
        if "name" in validated_data:
            validated_data["slug"] = slugify(validated_data["name"])
        return super().update(instance, validated_data)
