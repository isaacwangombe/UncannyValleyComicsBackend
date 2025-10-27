# products/admin.py
from django.contrib import admin
from .models import Category, Product, ProductImage

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name","parent")
    prepopulated_fields = {"slug": ("name",)}

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "category","is_active","sales_count")
    prepopulated_fields = {"slug": ("title",)}
    search_fields = ("title","description")

admin.site.register(ProductImage)
