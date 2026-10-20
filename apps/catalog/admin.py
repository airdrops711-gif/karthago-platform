"""Django admin registration for the catalogue.

Without this module the Django admin shows no model at all: the owner
logs in at ``/admin/`` and finds an empty site. The registration below
makes the raw models reachable for maintenance, while the day-to-day
platform operations stay in the superadmin console (``/admin-dashboard/``).
"""
from django.contrib import admin

from .models import (
    Category,
    MarginRule,
    Product,
    ProductImage,
    Store,
    StoreProduct,
    Supplier,
)


@admin.register(Store)
class StoreAdmin(admin.ModelAdmin):
    """The tenant registry."""

    list_display = ("name", "slug", "owner", "is_platform_default", "is_active")
    list_filter = ("is_platform_default", "is_active")
    search_fields = ("name", "slug", "owner__username")
    prepopulated_fields = {"slug": ("name",)}
    autocomplete_fields = ("owner",)


@admin.register(StoreProduct)
class StoreProductAdmin(admin.ModelAdmin):
    """A product as sold by one store."""

    list_display = (
        "title",
        "store",
        "selling_price",
        "display_rank",
        "is_featured_on_main",
        "featured_priority",
        "is_published",
    )
    list_filter = (
        "store",
        "is_published",
        "in_stock",
        "is_store_native",
        "is_featured_on_main",
    )
    search_fields = ("title", "slug", "category")
    autocomplete_fields = ("store", "scraped_source_product")
    readonly_fields = ("display_rank", "created_at", "updated_at")
    list_editable = ("is_featured_on_main", "featured_priority")


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    """The central scraped pool."""

    list_display = ("title", "category", "supplier", "raw_cost", "retail_price", "is_active")
    list_filter = ("is_active", "category", "supplier")
    search_fields = ("title", "source_id", "source")
    readonly_fields = ("created_at", "updated_at")


@admin.register(ProductImage)
class ProductImageAdmin(admin.ModelAdmin):
    list_display = ("product", "image", "is_primary", "order")
    list_filter = ("is_primary",)


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "source_hint", "icon")
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = ("name", "website", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name", "website")


@admin.register(MarginRule)
class MarginRuleAdmin(admin.ModelAdmin):
    list_display = ("name", "markup_percent", "fixed_margin_fee", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name",)
