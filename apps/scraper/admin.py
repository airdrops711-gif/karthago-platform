"""Django admin registration for the scraper control plane."""
from django.contrib import admin

from .models import ScrapedSource, ScraperLog


@admin.register(ScrapedSource)
class ScrapedSourceAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "engine",
        "base_url",
        "category_name",
        "is_active",
        "updated_at",
    )
    list_filter = ("engine", "is_active", "category_name")
    search_fields = ("name", "base_url")


@admin.register(ScraperLog)
class ScraperLogAdmin(admin.ModelAdmin):
    list_display = (
        "source",
        "status",
        "products_found",
        "products_updated",
        "started_at",
        "finished_at",
    )
    list_filter = ("status", "source")
    autocomplete_fields = ("source",)
    readonly_fields = ("started_at", "finished_at")
