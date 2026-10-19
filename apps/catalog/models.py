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
    currency = models.CharField(
        max_length=8, default="TND",
        help_text="Source currency of raw_cost (TND, EUR, USD...).",
    )
    currency_rate = models.DecimalField(
        max_digits=12, decimal_places=6, default=1,
        validators=[MinValueValidator(0)],
        help_text="Conversion rate from source currency to TND.",
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
        """Retail Price = (Source Cost * FX * (1 + Markup% / 100)) + Fixed Margin Fee."""
        from decimal import Decimal
        # Coerce everything to Decimal: model defaults may still hold int/float
        # on freshly instantiated objects, and Decimal + float raises TypeError.
        def dec(value):
            if value is None:
                return Decimal("0")
            if isinstance(value, Decimal):
                return value
            return Decimal(str(value))

        cost = dec(self.raw_cost)
        rate = dec(self.currency_rate) or Decimal("1")
        markup = dec(self.markup_percent)
        fixed = dec(self.fixed_margin_fee)
        cost_tnd = cost * rate
        result = (cost_tnd * (1 + markup / Decimal("100"))) + fixed
        return result.quantize(Decimal("0.001"))

    def save(self, *args, **kwargs):
        if not self.retail_price:
            self.retail_price = self.compute_retail_price()
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
