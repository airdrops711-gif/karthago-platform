"""Catalog models for Karthago Platform.

Three layers live here and must not be mixed up:

* ``Product`` — the *central scraped pool*. One global row per supplier
  item, shared by every store. The Celery scraper owns these rows.
* ``StoreProduct`` — the *tenant catalogue*. Every store has its own
  rows, either native (created by the vendor) or imported from the
  central pool. This is what the storefronts display.
* ``Store`` — the tenant itself: the platform flagship or a vendor
  sub-store.
"""
from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone
from django.utils.text import slugify


class Category(models.Model):
    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True)
    description = models.TextField(blank=True)
    # The supplier department this category mirrors (e.g. "Informatique",
    # "Homme"). Used by the storefront to group sources on the landing page.
    source_hint = models.CharField(
        max_length=100, blank=True,
        help_text="Supplier department this category mirrors.",
    )
    icon = models.CharField(
        max_length=8, blank=True,
        help_text="Emoji shown on the category showcase tiles.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Catégorie"
        verbose_name_plural = "Catégories"
        ordering = ["name"]

    def __str__(self):
        return self.name

    @property
    def product_count(self):
        """Number of active, in-stock products in this category."""
        return self.products.filter(is_active=True).count()


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
    # 500 chars: AliExpress product URLs reach ~700 chars with tracking params
    # before normalisation, and URLField defaults to 200.
    source = models.URLField(max_length=500, blank=True, help_text="Original supplier product URL.")
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
    compare_at_price = models.DecimalField(
        max_digits=10, decimal_places=3, default=0,
        validators=[MinValueValidator(0)],
        help_text="Supplier reference price before discount (0 = no reference).",
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
        # The retail price is always derived from the cost and the margin
        # rule, so it must be recomputed on every write. Keeping the old
        # value when the supplier cost changes would silently sell at the
        # wrong margin.
        self.retail_price = self.compute_retail_price()
        # update_or_create() narrows the write to the changed columns. The
        # recomputed price is not part of that set, so it has to be added
        # explicitly or the new margin would never reach the database.
        update_fields = kwargs.get("update_fields")
        if update_fields is not None:
            kwargs["update_fields"] = set(update_fields) | {"retail_price"}
        super().save(*args, **kwargs)

    @property
    def discount_percent(self):
        """Supplier discount in percent (0 when the item is not reduced)."""
        reference = self.compare_at_price or 0
        if reference <= 0 or self.raw_cost <= 0:
            return 0
        if self.raw_cost >= reference:
            return 0
        return round(((reference - self.raw_cost) / reference) * 100)


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
class Store(models.Model):
    """A tenant: the platform flagship or a vendor sub-store.

    Exactly one store carries ``is_platform_default=True`` — the
    flagship, which owns the root of the site (``/``) and the central
    scraped pool. Every other store is served under ``/s/<slug>/``.
    """

    owner = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="store",
        null=True,
        blank=True,
        help_text="Vendor account owning this store.",
    )
    name = models.CharField(max_length=150)
    slug = models.SlugField(max_length=180, unique=True)
    is_platform_default = models.BooleanField(
        default=False, help_text="True for the main flagship store."
    )
    tagline = models.CharField(max_length=200, blank=True)
    description = models.TextField(blank=True)
    logo_url = models.URLField(max_length=500, blank=True)
    phone_number = models.CharField(max_length=20, blank=True)
    whatsapp_number = models.CharField(max_length=20, blank=True)
    address = models.CharField(max_length=300, blank=True)
    default_markup_percentage = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal("25.00"),
        validators=[MinValueValidator(0)],
        help_text="Default markup applied to the vendor's own products.",
    )
    fixed_margin = models.DecimalField(
        max_digits=10, decimal_places=3, default=Decimal("0.000"),
        validators=[MinValueValidator(0)],
        help_text="Fixed margin added to every sale, in TND.",
    )
    is_active = models.BooleanField(default=True)

    # --- Operational lifecycle -----------------------------------------
    # ``status`` is the source of truth of the lifecycle; ``is_active``
    # is kept in sync with it for backward compatibility with the
    # console forms and the tenant middleware.
    STATUS_ACTIVE = "ACTIVE"
    STATUS_SUSPENDED = "SUSPENDED"
    STATUS_MAINTENANCE = "MAINTENANCE"

    STATUS_CHOICES = [
        (STATUS_ACTIVE, "Active / Operating"),
        (STATUS_SUSPENDED, "Suspended / Deactivated by Admin"),
        (STATUS_MAINTENANCE, "Store Inactive / Maintenance Mode"),
    ]

    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default=STATUS_ACTIVE,
        help_text="Operational status of the store.",
    )
    deactivation_reason = models.TextField(
        blank=True, null=True,
        help_text="Why the store was taken offline (shown to the vendor).",
    )
    deactivated_at = models.DateTimeField(null=True, blank=True)

    # --- Commission structure ------------------------------------------
    # In the Tunisian COD flow the platform fee is only realized when an
    # order reaches DELIVERED_AND_PAID, so the rule is configured per
    # store and applied at the moment of the delivery.
    COMMISSION_TYPE_PERCENT = "PERCENT"
    COMMISSION_TYPE_FLAT = "FLAT"
    COMMISSION_TYPE_HYBRID = "HYBRID"

    COMMISSION_TYPES = [
        (COMMISSION_TYPE_PERCENT, "Percentage of Gross Order Total"),
        (COMMISSION_TYPE_FLAT, "Fixed TND Fee per Delivered Order"),
        (COMMISSION_TYPE_HYBRID, "Percentage + Flat Fee"),
    ]

    commission_type = models.CharField(
        max_length=20, choices=COMMISSION_TYPES, default=COMMISSION_TYPE_PERCENT,
    )
    commission_rate = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal("5.00"),
        validators=[MinValueValidator(0)],
        help_text="Platform fee in percent of the gross order total.",
    )
    flat_fee_per_order = models.DecimalField(
        max_digits=10, decimal_places=3, default=Decimal("0.000"),
        validators=[MinValueValidator(0)],
        help_text="Fixed platform fee per delivered order, in TND.",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Boutique"
        verbose_name_plural = "Boutiques"

    def __str__(self):
        return f"{self.name} {'(Flagship)' if self.is_platform_default else ''}"

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        self._sync_lifecycle()
        super().save(*args, **kwargs)

    def _sync_lifecycle(self):
        """Keep ``status``, ``is_active`` and the deactivation fields aligned.

        * a non-active status always means an inactive store;
        * an active store that was flagged inactive is suspended;
        * the flagship can never be taken offline: it owns the root of
          the site, and suspending it would take the whole platform down.
        """
        if self.is_platform_default:
            self.is_active = True
            self.status = self.STATUS_ACTIVE
            self.deactivated_at = None
            return

        if self.status == self.STATUS_ACTIVE and not self.is_active:
            # The status was not touched but the store was flagged
            # inactive: this is a suspension.
            self.status = self.STATUS_SUSPENDED

        if self.status != self.STATUS_ACTIVE:
            self.is_active = False
            if not self.deactivated_at:
                self.deactivated_at = timezone.now()
        else:
            self.deactivated_at = None
            if not self.deactivation_reason:
                self.deactivation_reason = ""

    # -- lifecycle helpers ----------------------------------------------
    @property
    def is_operational(self):
        """True when the store may be browsed and searched."""
        return self.is_active and self.status == self.STATUS_ACTIVE

    @property
    def status_label(self):
        for code, label in self.STATUS_CHOICES:
            if code == self.status:
                return label
        return self.status

    def suspend(self, reason=""):
        """Take the store offline, with the reason shown to the vendor."""
        self.status = self.STATUS_SUSPENDED
        self.is_active = False
        self.deactivation_reason = (reason or "").strip()
        self.deactivated_at = timezone.now()
        self.save()

    def reactivate(self):
        """Put the store back online."""
        self.status = self.STATUS_ACTIVE
        self.is_active = True
        self.deactivation_reason = ""
        self.deactivated_at = None
        self.save()

    def commission_label(self):
        """Human readable commission rule of the store."""
        if self.commission_type == self.COMMISSION_TYPE_FLAT:
            return f"{self.flat_fee_per_order} DT / commande livrée"
        if self.commission_type == self.COMMISSION_TYPE_HYBRID:
            return (
                f"{self.commission_rate}% + {self.flat_fee_per_order} DT "
                "par commande livrée"
            )
        return f"{self.commission_rate}% du CA livré"

    @property
    def storefront_url(self):
        """Public URL of the store.

        The flagship lives at the root of the site; a sub-store lives
        under ``/s/<slug>/``.
        """
        if self.is_platform_default:
            return "/"
        return f"/s/{self.slug}/"

    def price_from_cost(self, cost, markup=None):
        """Selling price of a product costing ``cost`` TND.

        ``markup`` overrides the store default when the vendor set a
        custom markup on the product.
        """
        cost = Decimal(str(cost or 0))
        rate = Decimal(str(markup)) if markup is not None else self.default_markup_percentage
        return ((cost * (1 + rate / Decimal("100"))) + self.fixed_margin).quantize(
            Decimal("0.001")
        )


class ActiveStoreProductManager(models.Manager):
    """Only the products a visitor may actually see.

    A row survives this filter when it is published, in stock, and its
    store is operational (active *and* in the ACTIVE status). This is
    the queryset the storefront and the search use: the moment a store
    is suspended its products disappear from the catalogue, from the
    homepage showcase and from the search results.
    """

    def get_queryset(self):
        return super().get_queryset().filter(
            is_published=True,
            in_stock=True,
            store__is_active=True,
            store__status=Store.STATUS_ACTIVE,
        )


class StoreProduct(models.Model):
    """A product as sold by one store.

    A store-native product (created by the vendor, manually or by bulk
    import) has no link to the central pool. An imported one keeps a
    link to the scraped ``Product`` it was cloned from, so the origin
    stays traceable.
    """

    store = models.ForeignKey(Store, on_delete=models.CASCADE, related_name="store_products")
    # Optional link to the central scraped pool (null when the product
    # was created manually by the vendor).
    scraped_source_product = models.ForeignKey(
        "Product", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="store_instances",
    )
    title = models.CharField(max_length=300)
    slug = models.SlugField(max_length=350)
    description = models.TextField(blank=True)

    # Financial fields (Tunisian millimes: 3 decimal places).
    source_cost = models.DecimalField(
        max_digits=10, decimal_places=3, default=Decimal("0.000"),
        validators=[MinValueValidator(0)],
    )
    custom_markup = models.DecimalField(
        max_digits=5, decimal_places=2, blank=True, null=True,
        validators=[MinValueValidator(0)],
        help_text="Overrides the store default markup when set.",
    )
    selling_price = models.DecimalField(
        max_digits=10, decimal_places=3, default=Decimal("0.000"),
        validators=[MinValueValidator(0)],
    )
    image_url = models.URLField(max_length=500, blank=True)
    image_urls = models.JSONField(
        default=list, blank=True,
        help_text="Extra image URLs, as imported from the scraped pool.",
    )
    category = models.CharField(
        max_length=150, blank=True,
        help_text="Free-text category, kept per store to avoid a global taxonomy.",
    )
    external_url = models.URLField(max_length=500, blank=True)
    in_stock = models.BooleanField(default=True)
    is_published = models.BooleanField(default=True)
    is_store_native = models.BooleanField(
        default=False, help_text="True if created manually/bulk by the vendor."
    )
    # Persisted display tier, so the flagship listing can be ordered by the
    # tenant tiers straight from the database: 0 = curated on the main
    # platform, 1 = native inventory, 2 = imported from the central pool.
    display_rank = models.PositiveSmallIntegerField(
        default=2, editable=False,
        help_text="0 = curated on main, 1 = native, 2 = imported.",
    )

    # --- Cross-store curation fields for the main platform ---
    is_featured_on_main = models.BooleanField(
        default=False,
        help_text="Flagged by the superadmin to feature on the main platform homepage.",
    )
    featured_priority = models.PositiveIntegerField(
        default=0,
        help_text="Weight order for the featured placement (higher = higher position).",
    )
    featured_curated_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("store", "slug")
        ordering = ["-featured_priority", "-created_at"]
        verbose_name = "Produit de boutique"
        verbose_name_plural = "Produits de boutique"
        indexes = [
            models.Index(fields=["store", "is_published"]),
            models.Index(fields=["is_featured_on_main", "featured_priority"]),
        ]

    # ``objects`` stays unfiltered: the dashboards and the admin need
    # the suspended products too (to show them, count them, restore
    # them). ``active_objects`` is the public view.
    objects = models.Manager()
    active_objects = ActiveStoreProductManager()

    def __str__(self):
        return f"{self.title} ({self.store.name})"

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.title)[:340] or "produit"
            slug = base
            index = 2
            while (
                StoreProduct.objects.filter(store=self.store, slug=slug)
                .exclude(pk=self.pk)
                .exists()
            ):
                slug = f"{base}-{index}"
                index += 1
            self.slug = slug
        if not self.selling_price:
            self.selling_price = self.calculate_price()
        self.display_rank = self.compute_display_rank()
        update_fields = kwargs.get("update_fields")
        if update_fields is not None:
            kwargs["update_fields"] = set(update_fields) | {"display_rank"}
        super().save(*args, **kwargs)

    def compute_display_rank(self):
        """The tenant display tier of this product.

        0 — curated by the superadmin for the main platform.
        1 — native inventory of the store.
        2 — imported from the central scraped pool.
        """
        if self.is_featured_on_main:
            return 0
        if self.is_store_native:
            return 1
        return 2

    def calculate_price(self):
        """Selling price computed from the source cost and the markup."""
        return self.store.price_from_cost(self.source_cost, self.custom_markup)

    @property
    def margin_amount(self):
        """Gross margin of the product, in TND."""
        return (self.selling_price or Decimal("0")) - (self.source_cost or Decimal("0"))

    @property
    def margin_percent(self):
        """Gross margin of the product, in percent of the selling price."""
        if not self.selling_price:
            return 0
        return round((self.margin_amount / self.selling_price) * 100, 2)

    @property
    def tier_rank(self):
        """Display tier used by the priority ranking.

        1 = store-native inventory, 2 = imported from the central pool.
        """
        return 1 if self.is_store_native else 2

    @property
    def vendor_badge(self):
        """Name of the store selling this product."""
        return self.store.name
