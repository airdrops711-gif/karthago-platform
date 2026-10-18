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
    status = models.CharField(max_length=20, default="running")

    def __str__(self):
        return f"{self.source.name} - {self.started_at}"
