from django.db.models.signals import post_delete
from django.dispatch import receiver
from .models import ProductImage, Product
import cloudinary.uploader


@receiver(post_delete, sender=ProductImage)
def delete_cloudinary_image(sender, instance, **kwargs):
    """
    Automatically delete image from Cloudinary when a ProductImage is deleted.
    """
    if instance.image and hasattr(instance.image, "public_id"):
        try:
            cloudinary.uploader.destroy(instance.image.public_id)
            print(f"🗑️ Deleted image {instance.image.public_id} from Cloudinary.")
        except Exception as e:
            print(f"⚠️ Cloudinary deletion failed: {e}")


@receiver(post_delete, sender=Product)
def delete_product_images_from_cloudinary(sender, instance, **kwargs):
    """
    Automatically delete all Cloudinary images related to a Product when the Product is deleted.
    """
    for image in instance.images.all():
        if image.image and hasattr(image.image, "public_id"):
            try:
                cloudinary.uploader.destroy(image.image.public_id)
                print(f"🗑️ Deleted image {image.image.public_id} from Cloudinary (Product deleted).")
            except Exception as e:
                print(f"⚠️ Failed to delete product image from Cloudinary: {e}")
