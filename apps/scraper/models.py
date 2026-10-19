"""Scraper models for Karthago Platform."""
from django.db import models


class ScrapedSource(models.Model):
    ENGINE_STATIC = "STATIC"
    ENGINE_DYNAMIC = "DYNAMIC"
    ENGINE_CHOICES = [
        (ENGINE_STATIC, "Static (HTTPX + Selectolax)"),
        (ENGINE_DYNAMIC, "Dynamic (Playwright)"),
    ]

    name = models.CharField(max_length=100)
    base_url = models.URLField()
    engine = models.CharField(max_length=10, choices=ENGINE_CHOICES, default=ENGINE_STATIC)
    product_container_selector = models.CharField(max_length=255)
    title_selector = models.CharField(max_length=255)
    price_selector = models.CharField(max_length=255)
    stock_selector = models.CharField(max_length=255, blank=True)
    images_selector = models.CharField(max_length=255, blank=True)
    brand_selector = models.CharField(max_length=255, blank=True)
    model_selector = models.CharField(max_length=255, blank=True)
    category_selector = models.CharField(max_length=255, blank=True)
    currency = models.CharField(max_length=8, default="TND", help_text="Source currency.")
    currency_rate = models.DecimalField(
        max_digits=12, decimal_places=6, default=1,
        help_text="Conversion rate from source currency to TND.",
    )
    category_name = models.CharField(
        max_length=100, blank=True,
        help_text="Category assigned to scraped products.",
    )
    sync_frequency_hours = models.PositiveIntegerField(default=4, help_text="Sync every N hours.")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Scraped Source"
        verbose_name_plural = "Scraped Sources"

    def __str__(self):
        return self.name


class ScraperLog(models.Model):
    source = models.ForeignKey(
        ScrapedSource, on_delete=models.CASCADE, related_name="logs"
    )
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    products_found = models.PositiveIntegerField(default=0)
    products_updated = models.PositiveIntegerField(default=0)
    errors = models.TextField(blank=True)
    status = models.CharField(max_length=30, default="running")

    def __str__(self):
        return f"{self.source.name} - {self.started_at}"
