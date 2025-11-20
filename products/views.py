# products/views.py
from rest_framework import viewsets, permissions, filters, status, parsers
from django_filters.rest_framework import DjangoFilterBackend
from .models import Product, Category, ProductImage, UPCOMING_CATEGORY_ID, PAST_CATEGORY_ID
from .serializers import ProductSerializer, CategorySerializer, ProductImageSerializer
from .permissions import IsAdminOrReadOnly
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response
from rest_framework.permissions import IsAdminUser
from rest_framework.decorators import action, api_view, permission_classes, parser_classes
from cloudinary.uploader import destroy, upload as cloudinary_upload
from django.http import HttpResponse
import io
import pandas as pd
import zipfile
import os
import requests
from decimal import Decimal
from django.utils import timezone

# Product ViewSet
class ProductViewSet(viewsets.ModelViewSet):
    queryset = Product.objects.all().select_related("category", "event_data").prefetch_related("images")
    serializer_class = ProductSerializer

    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ["category", "category__parent", "category__slug", "category__parent__slug", "is_active", "trending"]
    search_fields = ["title", "description"]
    ordering_fields = ["sales_count", "created_at", "price", "stock"]

    def get_permissions(self):
        if self.action in ["create", "update", "partial_update", "destroy", "bulk_upload"]:
            return [permissions.IsAdminUser()]
        return [permissions.AllowAny()]

    def _maybe_move_to_past(self, product):
        """
        If product has event_data and its end < now (or start < now when end missing),
        move product.category to PAST_CATEGORY_ID.
        """
        try:
            event = getattr(product, "event_data", None)
            if not event:
                return False

            now = timezone.now()
            if event.end:
                if event.end < now and product.category_id != PAST_CATEGORY_ID:
                    product.category_id = PAST_CATEGORY_ID
                    product.save(update_fields=["category"])
                    return True
            else:
                # fallback to start
                if event.start and event.start < now and product.category_id != PAST_CATEGORY_ID:
                    product.category_id = PAST_CATEGORY_ID
                    product.save(update_fields=["category"])
                    return True
        except Exception:
            pass
        return False

    def list(self, request, *args, **kwargs):
        # On listing, ensure up-to-date categories for event products
        qs = self.filter_queryset(self.get_queryset())

        # iterate and potentially update some products
        for p in qs:
            self._maybe_move_to_past(p)

        page = self.paginate_queryset(qs)
        if page is not None:
            serializer = self.get_serializer(page, many=True, context={"request": request})
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(qs, many=True, context={"request": request})
        return Response(serializer.data)

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        # ensure category updated for this product if needed
        self._maybe_move_to_past(instance)
        serializer = self.get_serializer(instance)
        return Response(serializer.data)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        product = serializer.save()

        # maybe move to past after update (serializer already set category appropriately)
        self._maybe_move_to_past(product)

        # auto-disable if stock is 0
        if product.stock <= 0 and product.is_active:
            product.is_active = False
            product.save(update_fields=["is_active"])

        return Response(self.get_serializer(product).data)

    def create(self, request, *args, **kwargs):
        # Use serializer create logic (it will set category based on event_data)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        product = serializer.save()

        # maybe move to past if event end already passed
        self._maybe_move_to_past(product)

        headers = self.get_success_headers(serializer.data)
        return Response(self.get_serializer(product).data, status=status.HTTP_201_CREATED, headers=headers)

    @action(detail=True, methods=["post"], permission_classes=[permissions.IsAdminUser])
    def toggle_trending(self, request, pk=None):
        product = self.get_object()
        product.trending = not product.trending
        product.save(update_fields=["trending"])
        return Response({"id": product.id, "trending": product.trending}, status=status.HTTP_200_OK)

    @action(detail=False, methods=["get"], permission_classes=[permissions.IsAdminUser])
    def low_stock(self, request):
        low = Product.objects.filter(stock__lt=5).values("id", "title", "stock", "sales_count")
        return Response(list(low))


@api_view(["POST"])
@permission_classes([IsAdminUser])
@parser_classes([MultiPartParser, FormParser])
def bulk_upload_products(request):
    """
    Bulk upload supports event columns:
    - event_start, event_end, event_location
    It will set product.category to UPCOMING_CATEGORY_ID or PAST_CATEGORY_ID based on dates.
    """
    excel_file = request.FILES.get("excel_file")
    zip_file = request.FILES.get("images_zip")

    if not excel_file:
        return Response({"error": "Excel file is required."}, status=status.HTTP_400_BAD_REQUEST)

    try:
        df = pd.read_excel(excel_file)
        created, skipped = [], []
        zip_images = {}

        if zip_file:
            try:
                with zipfile.ZipFile(zip_file, "r") as zf:
                    for filename in zf.namelist():
                        if filename.lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
                            clean_name = os.path.basename(filename).lower().strip()
                            zip_images[clean_name] = zf.read(filename)
            except zipfile.BadZipFile:
                return Response({"error": "Invalid ZIP file."}, status=status.HTTP_400_BAD_REQUEST)

        for _, row in df.iterrows():
            title = str(row.get("title", "")).strip()
            if not title:
                continue

            description = str(row.get("description", "")).strip()
            try:
                price = Decimal(row.get("price", 0)) if not pd.isna(row.get("price")) else Decimal("0.00")
            except Exception:
                price = Decimal("0.00")
            try:
                cost = Decimal(row.get("cost")) if not pd.isna(row.get("cost")) else None
            except Exception:
                cost = None
            try:
                discounted_price = Decimal(row.get("discounted_price")) if not pd.isna(row.get("discounted_price")) else None
            except Exception:
                discounted_price = None

            try:
                stock = int(row.get("stock", 0))
            except Exception:
                stock = 0

            category_slug = str(row.get("category_slug", "")).strip().lower()
            trending = bool(row.get("trending", False))
            sku = str(row.get("sku", "")).strip() or None

            # Event columns
            event_start = row.get("event_start", None)
            event_end = row.get("event_end", None)
            event_location = row.get("event_location", None)

            # Normalize datetimes
            try:
                if not pd.isna(event_start) and event_start is not None:
                    event_start = pd.to_datetime(event_start)
                else:
                    event_start = None
            except Exception:
                event_start = None

            try:
                if not pd.isna(event_end) and event_end is not None:
                    event_end = pd.to_datetime(event_end)
                else:
                    event_end = None
            except Exception:
                event_end = None

            # Determine category: if event columns present -> Up-Coming or Past based on dates
            is_event_row = bool(event_start or event_end)
            category_obj = None
            if is_event_row:
                # Decide past/upcoming
                now = timezone.now()
                cat_id = UPCOMING_CATEGORY_ID
                if event_end:
                    if event_end < now:
                        cat_id = PAST_CATEGORY_ID
                else:
                    if event_start and event_start < now:
                        cat_id = PAST_CATEGORY_ID
                try:
                    category_obj = Category.objects.get(pk=cat_id)
                except Category.DoesNotExist:
                    category_obj = None

            if not category_obj:
                # fallback: try to get by slug from sheet
                try:
                    category_obj = Category.objects.get(slug=category_slug)
                except Category.DoesNotExist:
                    skipped.append(f"{title} (invalid category)")
                    continue

            # Create the product
            product = Product.objects.create(
                title=title,
                description=description,
                price=price,
                cost=cost,
                discounted_price=discounted_price,
                stock=stock,
                category=category_obj,
                is_active=stock > 0,
                trending=trending,
                sku=sku,
            )

            # Create EventExtension if event row
            if is_event_row:
                try:
                    EventExtension.objects.create(
                        product=product,
                        start=event_start or timezone.now(),
                        end=event_end,
                        location=event_location or "",
                    )
                except Exception as e:
                    print(f"⚠️ Failed to create EventExtension for {title}: {e}")

            # Images handling (same as before) ...
            image_field = row.get("images", None)
            if (not image_field) and zip_images and sku:
                possible = [k for k in zip_images.keys() if k.startswith(sku.lower())]
                if possible:
                    image_field = ",".join(possible)

            if image_field:
                image_names = [n.strip() for n in str(image_field).split(",") if n.strip()]
                for name in image_names:
                    match = None
                    if name.startswith("http://") or name.startswith("https://"):
                        try:
                            response = requests.get(name, timeout=10)
                            if response.status_code == 200:
                                file_obj = io.BytesIO(response.content)
                                file_obj.name = os.path.basename(name.split("?")[0])
                                file_obj.seek(0)
                                upload_result = cloudinary_upload(
                                    file_obj,
                                    folder=f"products/{product.sku or product.id}",
                                    resource_type="image",
                                    public_id=os.path.splitext(file_obj.name)[0],
                                    overwrite=True,
                                    transformation=[{"quality": "auto:eco", "fetch_format": "auto", "width": 1200, "crop": "limit"}],
                                )
                                ProductImage.objects.create(product=product, image=upload_result["secure_url"])
                        except Exception as e:
                            print(f"⚠️ Error fetching URL {name}: {e}")
                        continue

                    name_lower = name.lower()
                    if zip_images:
                        match = zip_images.get(name_lower)
                        if not match:
                            base = os.path.splitext(name_lower)[0]
                            for variant in zip_images.keys():
                                if variant.startswith(base):
                                    match = zip_images[variant]
                                    break

                    if match:
                        file_obj = io.BytesIO(match)
                        file_obj.name = os.path.basename(name_lower)
                        file_obj.seek(0)
                        try:
                            upload_result = cloudinary_upload(
                                file_obj,
                                folder=f"products/{product.sku or product.id}",
                                resource_type="image",
                                public_id=os.path.splitext(file_obj.name)[0],
                                overwrite=True,
                                transformation=[{"quality": "auto:eco", "fetch_format": "auto", "width": 1200, "crop": "limit"}],
                            )
                            ProductImage.objects.create(product=product, image=upload_result["secure_url"])
                        except Exception as e:
                            print(f"⚠️ Cloudinary upload failed for {name}: {e}")

            created.append(product.title)

        return Response(
            {
                "message": f"✅ {len(created)} products created successfully.",
                "created_products": created,
                "skipped": skipped,
                "images_uploaded": len(zip_images),
            },
            status=status.HTTP_201_CREATED,
        )

    except Exception as e:
        print("❌ Bulk upload failed:", e)
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
@api_view(["GET"])
@permission_classes([IsAdminUser])
def download_sample_excel(request):
    """
    📄 Download a sample Excel matching the current bulk upload format.
    Includes:
        - title
        - description
        - price
        - cost
        - discounted_price
        - stock
        - is_event
        - event_start
        - event_end
        - event_location
        - images
        - sku
    """
    data = {
        "title": ["Sample Event Product"],
        "description": ["This is an example of an event product."],
        "price": [20.00],
        "cost": [10.00],
        "discounted_price": [15.00],
        "stock": [50],  # also acts as event capacity
        "is_event": [True],
        "event_start": ["2025-06-05 18:00"],
        "event_end": ["2025-06-05 21:00"],
        "event_location": ["Sample Venue"],
        "images": ["example.jpg"], 
        "sku": ["EVT-001"],
    }

    df = pd.DataFrame(data)

    output = io.BytesIO()

    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        df.to_excel(writer, index=False, sheet_name="Products")
        worksheet = writer.sheets["Products"]

        # autosize columns
        for i, col in enumerate(df.columns):
            col_width = max(df[col].astype(str).map(len).max(), len(col)) + 2
            worksheet.set_column(i, i, col_width)

    output.seek(0)
    response = HttpResponse(
        output.read(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = 'attachment; filename="sample_products.xlsx"'
    return response


# The ProductImageViewSet and CategoryViewSet remain the same as before (unchanged).
from rest_framework import serializers
from rest_framework.decorators import action
from cloudinary.uploader import destroy

class ProductImageViewSet(viewsets.ModelViewSet):
    queryset = ProductImage.objects.all()
    serializer_class = ProductImageSerializer
    permission_classes = [IsAdminUser]
    parser_classes = [MultiPartParser, FormParser]

    def perform_create(self, serializer):
        product_id = self.request.data.get("product")
        if not product_id:
            raise serializers.ValidationError({"product": "Product ID is required."})
        serializer.save(product_id=product_id)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance.image and "upload/" in str(instance.image):
            public_id = str(instance.image).split("upload/")[-1].split(".")[0]
            try:
                destroy(public_id)
            except Exception as e:
                print(f"⚠️ Cloudinary delete failed: {e}")
        instance.delete()
        return Response({"detail": "Image deleted successfully."}, status=status.HTTP_204_NO_CONTENT)


class CategoryViewSet(viewsets.ModelViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    parser_classes = [parsers.MultiPartParser, parsers.FormParser, parsers.JSONParser]

    def get_permissions(self):
        if self.action in ["create", "update", "partial_update", "destroy", "delete_image"]:
            return [permissions.IsAdminUser()]
        return [permissions.AllowAny()]

    @action(detail=True, methods=["delete"], url_path="delete-image")
    def delete_image(self, request, pk=None):
        category = self.get_object()
        if not category.image:
            return Response({"detail": "No image to delete."}, status=status.HTTP_400_BAD_REQUEST)

        public_id = str(category.image.public_id)
        destroy(public_id)
        category.image = None
        category.save(update_fields=["image"])
        return Response({"detail": "Image deleted successfully."}, status=status.HTTP_200_OK)
