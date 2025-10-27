from rest_framework import viewsets, permissions, filters, status, parsers
from django_filters.rest_framework import DjangoFilterBackend
from .models import Product, Category, ProductImage
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



# ✅ Product ViewSet
class ProductViewSet(viewsets.ModelViewSet):
    queryset = Product.objects.all().prefetch_related("images", "category")
    serializer_class = ProductSerializer

    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ["category", "category__parent", "category__slug", "category__parent__slug", "is_active", "trending"]
    search_fields = ["title", "description"]
    ordering_fields = ["sales_count", "created_at", "price", "stock"]

    def get_permissions(self):
        """Dynamic permissions: staff can edit, anyone can view"""
        if self.action in ["create", "update", "partial_update", "destroy", "bulk_upload"]:
            return [permissions.IsAdminUser()]
        return [permissions.AllowAny()]

    def update(self, request, *args, **kwargs):
        """Ensure auto-deactivate when stock is 0"""
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        product = serializer.save()

        # 🧠 Auto-disable if stock is 0
        if product.stock <= 0 and product.is_active:
            product.is_active = False
            product.save(update_fields=["is_active"])

        return Response(serializer.data)

    @action(detail=True, methods=["post"], permission_classes=[permissions.IsAdminUser])
    def toggle_trending(self, request, pk=None):
        """Toggle 'trending' boolean on a product."""
        product = self.get_object()
        product.trending = not product.trending
        product.save(update_fields=["trending"])
        return Response(
            {"id": product.id, "trending": product.trending},
            status=status.HTTP_200_OK,
        )


@api_view(["POST"])
@permission_classes([IsAdminUser])
@parser_classes([MultiPartParser, FormParser])
def bulk_upload_products(request):
    """
    📦 Bulk upload products via Excel and optional ZIP or image URLs.
    - Excel required (.xlsx)
    - ZIP optional
    - Supports:
        ✅ Image URLs (https://...)
        ✅ ZIP-based uploads
        ✅ SKU-based auto-link when `images` blank
    """
    import requests

    excel_file = request.FILES.get("excel_file")
    zip_file = request.FILES.get("images_zip")

    if not excel_file:
        return Response({"error": "Excel file is required."}, status=status.HTTP_400_BAD_REQUEST)

    try:
        df = pd.read_excel(excel_file)
        created, skipped = [], []
        zip_images = {}

        # ✅ Load and normalize image files from ZIP
        if zip_file:
            try:
                with zipfile.ZipFile(zip_file, "r") as zf:
                    for filename in zf.namelist():
                        if filename.lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
                            clean_name = os.path.basename(filename).lower().strip()
                            zip_images[clean_name] = zf.read(filename)
                print(f"📦 Loaded {len(zip_images)} image files from ZIP.")
            except zipfile.BadZipFile:
                return Response({"error": "Invalid ZIP file."}, status=status.HTTP_400_BAD_REQUEST)

        # ✅ Process each product in Excel
        for _, row in df.iterrows():
            title = str(row.get("title", "")).strip()
            if not title:
                continue

            description = str(row.get("description", "")).strip()
            price = float(row.get("price", 0))
            stock = int(row.get("stock", 0))
            category_slug = str(row.get("category_slug", "")).strip().lower()
            trending = bool(row.get("trending", False))
            sku = str(row.get("sku", "")).strip() or None

            # Get category safely
            try:
                category = Category.objects.get(slug=category_slug)
            except Category.DoesNotExist:
                skipped.append(f"{title} (invalid category)")
                continue

            # 🧠 Create the product
            product = Product.objects.create(
                title=title,
                description=description,
                price=price,
                stock=stock,
                category=category,
                is_active=stock > 0,
                trending=trending,
                sku=sku,
            )

            # --- IMAGE HANDLING ---
            image_field = row.get("images", None)

            # 🪄 If no images column, try auto-link by SKU prefix
            if not image_field and zip_images and sku:
                possible = [k for k in zip_images.keys() if k.startswith(sku.lower())]
                if possible:
                    image_field = ",".join(possible)
                    print(f"🪄 Auto-linked {len(possible)} images for {title}: {image_field}")

            # ✅ If we have any image data (URLs or filenames)
            if image_field:
                image_names = [n.strip() for n in str(image_field).split(",") if n.strip()]

                for name in image_names:
                    match = None

                    # --- CASE 1: full URL (download and upload) ---
                    if name.startswith("http://") or name.startswith("https://"):
                        try:
                            print(f"🌐 Downloading image from URL: {name}")
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
                                ProductImage.objects.create(
                                    product=product, image=upload_result["secure_url"]
                                )
                                print(f"✅ Uploaded URL image for {title}")
                            else:
                                print(f"⚠️ Failed to fetch image from URL: {name}")
                        except Exception as e:
                            print(f"⚠️ Error fetching URL {name}: {e}")
                        continue

                    # --- CASE 2: ZIP file match ---
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
                            ProductImage.objects.create(
                                product=product, image=upload_result["secure_url"]
                            )
                            print(f"✅ Uploaded ZIP image for {title}: {name}")
                        except Exception as e:
                            print(f"⚠️ Cloudinary upload failed for {name}: {e}")
                    else:
                        print(f"⚠️ No match found for {name}")

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


# ✅ Sample Excel Download
@api_view(["GET"])
@permission_classes([IsAdminUser])
def download_sample_excel(request):
    """
    📄 Downloadable sample Excel with SKU formula and sample fields.
    """
    data = {
        "title": ["Example Product"],
        "description": ["Short description"],
        "price": [9.99],
        "stock": [10],
        "category_slug": ["example-category"],
        "trending": [False],
        "images": ["example1.jpg, example1(2).jpg"],
        "sku": ["=UPPER(LEFT(SUBSTITUTE(A2,\" \",\"\"),5)) & \"-\" & TEXT(ROW(A2)-1,\"000\")"],
    }

    df = pd.DataFrame(data)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        df.to_excel(writer, index=False, sheet_name="Products")

    output.seek(0)
    response = HttpResponse(
        output.read(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = 'attachment; filename="sample_products.xlsx"'
    return response


# ✅ Product Image ViewSet
class ProductImageViewSet(viewsets.ModelViewSet):
    queryset = ProductImage.objects.all()
    serializer_class = ProductImageSerializer
    permission_classes = [IsAdminUser]
    parser_classes = [MultiPartParser, FormParser]

    def perform_create(self, serializer):
        """Link uploaded image to the correct product."""
        product_id = self.request.data.get("product")
        if not product_id:
            raise serializers.ValidationError({"product": "Product ID is required."})
        serializer.save(product_id=product_id)

    def destroy(self, request, *args, **kwargs):
        """
        ✅ Custom delete: remove from Cloudinary and database.
        """
        instance = self.get_object()
        if instance.image and "upload/" in str(instance.image):
            public_id = str(instance.image).split("upload/")[-1].split(".")[0]
            try:
                destroy(public_id)
            except Exception as e:
                print(f"⚠️ Cloudinary delete failed: {e}")
        instance.delete()
        return Response({"detail": "Image deleted successfully."}, status=status.HTTP_204_NO_CONTENT)


# ✅ Category ViewSet (unchanged except for imports)
class CategoryViewSet(viewsets.ModelViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    parser_classes = [parsers.MultiPartParser, parsers.FormParser, parsers.JSONParser]

    def get_permissions(self):
        """Dynamic permissions: staff can edit, anyone can view"""
        if self.action in ["create", "update", "partial_update", "destroy", "delete_image"]:
            return [permissions.IsAdminUser()]
        return [permissions.AllowAny()]

    @action(detail=True, methods=["delete"], url_path="delete-image")
    def delete_image(self, request, pk=None):
        """Delete a category's image from Cloudinary and clear it."""
        category = self.get_object()
        if not category.image:
            return Response({"detail": "No image to delete."}, status=status.HTTP_400_BAD_REQUEST)

        public_id = str(category.image.public_id)
        destroy(public_id)
        category.image = None
        category.save(update_fields=["image"])
        return Response({"detail": "Image deleted successfully."}, status=status.HTTP_200_OK)
