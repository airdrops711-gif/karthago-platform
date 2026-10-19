"""Catalog models for Karthago Platform."""
from django.db import models
from django.core.validators import MinValueValidator


class Category(models.Model):
    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = "Categories"
        ordering = ["name"]

    def __str__(self):
        return self.name


class Supplier(models.Model):
    name = models.CharField(max_length=100)
    website = models.URLField(blank=True)
    contact_email = models.EmailField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class MarginRule(models.Model):
    """Pricing rules applied per supplier or category."""
    name = models.CharField(max_length=100)
    markup_percent = models.DecimalField(
        max_digits=5, decimal_places=2, default=0,
        validators=[MinValueValidator(0)],
        help_text="Markup percentage applied to source cost.",
    )
    fixed_margin_fee = models.DecimalField(
        max_digits=10, decimal_places=3, default=0,
        validators=[MinValueValidator(0)],
        help_text="Fixed margin fee added in TND (3 decimals for millimes).",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class Product(models.Model):
    category = models.ForeignKey(
        Category, on_delete=models.SET_NULL, null=True, blank=True, related_name="products"
    )
    supplier = models.ForeignKey(
        Supplier, on_delete=models.SET_NULL, null=True, blank=True, related_name="products"
    )
    margin_rule = models.ForeignKey(
        MarginRule, on_delete=models.SET_NULL, null=True, blank=True, related_name="products"
    )
    source = models.URLField(blank=True, help_text="Original supplier product URL.")
    source_id = models.CharField(max_length=255, blank=True, help_text="External supplier product ID.")
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    raw_cost = models.DecimalField(
        max_digits=10, decimal_places=3, default=0,
        validators=[MinValueValidator(0)],
        help_text="Source cost in TND.",
    )
    markup_percent = models.DecimalField(
        max_digits=5, decimal_places=2, default=0,
        validators=[MinValueValidator(0)],
    )
    fixed_margin_fee = models.DecimalField(
        max_digits=10, decimal_places=3, default=0,
        validators=[MinValueValidator(0)],
        help_text="Fixed margin fee in TND.",
    )
    retail_price = models.DecimalField(
        max_digits=10, decimal_places=3, default=0,
        validators=[MinValueValidator(0)],
        help_text="Computed retail price in TND.",
    )
    stock = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    sync_to_meilisearch = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title

    def compute_retail_price(self):
        """Retail Price = (Source Cost * (1 + Markup% / 100)) + Fixed Margin Fee."""
        from decimal import Decimal
        cost = self.raw_cost or Decimal("0")
        markup = self.markup_percent or Decimal("0")
        fixed = self.fixed_margin_fee or Decimal("0")
        return (cost * (1 + markup / Decimal("100"))) + fixed

    def save(self, *args, **kwargs):
        if not self.retail_price:
            self.retail_price = self.compute_retail_price()
        self.is_active = self.stock > 0
        super().save(*args, **kwargs)


class ProductImage(models.Model):
    """Product images for gallery/carousel display."""
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name="images"
    )
    image = models.URLField(blank=True, help_text="Image URL.")
    alt_text = models.CharField(max_length=255, blank=True)
    is_primary = models.BooleanField(default=False)
    order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["order", "created_at"]

    def __str__(self):
        return f"Image for {self.product.title}"

    @property
    def url(self):
        return self.image or ""
