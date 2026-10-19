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
    price_fallbacks = models.JSONField(
        default=list, blank=True,
        help_text="Extra price selectors tried when the primary one yields nothing.",
    )
    price_strategy = models.CharField(
        max_length=10, default="first",
        choices=[
            ("first", "First match (regular price)"),
            ("last", "Last match (sale price)"),
            ("min", "Lowest match"),
            ("max", "Highest match"),
        ],
        help_text="How to pick the price when a container exposes several amounts.",
    )
    compare_at_price_selector = models.CharField(
        max_length=255, blank=True,
        help_text="Selector of the struck-through reference price, if any.",
    )
    price_text_mode = models.CharField(
        max_length=10, default="deep",
        choices=[
            ("deep", "Deep text (all descendants)"),
            ("shallow", "Direct text only"),
        ],
        help_text=(
            "How the price node text is read. Shopify mixes the original "
            "price into the deep text of the sale price node."
        ),
    )
    pagination_next_selector = models.CharField(
        max_length=255, blank=True,
        help_text="Selector of the 'next page' link, if the shop paginates.",
    )
    api_path = models.CharField(
        max_length=100, blank=True,
        help_text="Optional JSON catalogue endpoint (e.g. /products.json).",
    )
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
    category_icon = models.CharField(
        max_length=8, blank=True,
        help_text="Emoji shown on the storefront category tiles.",
    )
    source_hint = models.CharField(
        max_length=100, blank=True,
        help_text="Supplier department this source mirrors (e.g. Mode Femme).",
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
