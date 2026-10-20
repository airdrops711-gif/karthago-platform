"""Order models for Karthago Platform (Tunisian COD flow)."""
from decimal import Decimal

from django.db import models
from django.core.validators import MinValueValidator
from .constants import TUNISIAN_GOVERNORATES

# Readable brand for each scraped source prefix. The raw supplier name is
# the scraper source key ("tunisianet_smartphones"), which is not what the
# operator wants to read on a command sheet.
SUPPLIER_BRANDS = {
    "tunisianet": "Tunisianet",
    "twenty": "Twenty",
    "noonclo": "Noonclo",
    "wamia": "Wamia",
}
from apps.catalog.models import Product, Store, StoreProduct


class Customer(models.Model):
    full_name = models.CharField(max_length=200)
    phone = models.CharField(max_length=20, help_text="Tunisian phone number.")
    email = models.EmailField(blank=True)
    governorate = models.CharField(max_length=50, choices=TUNISIAN_GOVERNORATES)
    address = models.TextField()
    # The store the customer bought from. Null for the legacy rows that
    # predate the multi-tenant model; the data migration backfills them.
    store = models.ForeignKey(
        Store, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="customers",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.full_name


class Order(models.Model):
    STATUS_PENDING_CONFIRMATION = "PENDING_CONFIRMATION"
    STATUS_CONFIRMED = "CONFIRMED"
    STATUS_ORDERED_FROM_SUPPLIER = "ORDERED_FROM_SUPPLIER"
    STATUS_SHIPPED = "SHIPPED"
    STATUS_DELIVERED_AND_PAID = "DELIVERED_AND_PAID"
    STATUS_RETURNED = "RETURNED"

    STATUS_CHOICES = [
        (STATUS_PENDING_CONFIRMATION, "Pending Confirmation"),
        (STATUS_CONFIRMED, "Confirmed"),
        (STATUS_ORDERED_FROM_SUPPLIER, "Ordered From Supplier"),
        (STATUS_SHIPPED, "Shipped"),
        (STATUS_DELIVERED_AND_PAID, "Delivered & Paid"),
        (STATUS_RETURNED, "Returned (Retour)"),
    ]

    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name="orders")
    # The store that owns the order. Null for the legacy rows that predate
    # the multi-tenant model; the data migration backfills them with the
    # flagship.
    store = models.ForeignKey(
        Store, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="orders",
    )
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default=STATUS_PENDING_CONFIRMATION)
    total_amount = models.DecimalField(
        max_digits=10, decimal_places=3, default=0, validators=[MinValueValidator(0)],
        help_text="Total charged to the customer, in TND.",
    )
    total_cost = models.DecimalField(
        max_digits=10, decimal_places=3, default=0, validators=[MinValueValidator(0)],
        help_text="Snapshot of the supplier cost of the items, converted to TND.",
    )
    payment_method = models.CharField(max_length=20, default="COD")
    notes = models.TextField(blank=True, help_text="Internal notes for the operator.")
    confirmed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Order {self.id} - {self.customer.full_name}"

    @property
    def margin(self):
        """Gross margin of the order in TND (retail minus supplier cost)."""
        return self.total_amount - self.total_cost

    @property
    def margin_percent(self):
        """Gross margin of the order in percent of the retail price."""
        if not self.total_amount:
            return 0
        return round((self.margin / self.total_amount) * 100, 2)

    @property
    def item_count(self):
        """Total number of physical items in the order."""
        return sum(item.quantity for item in self.items.all())


class OrderItem(models.Model):
    """A line of the order.

    The supplier identity, the original cost and the source URL are
    *snapshotted* at checkout time: a later re-scrape of the catalogue may
    change the product price, but the historical order must keep the price
    that was actually charged.
    """

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    # The tenant product that was bought. Kept nullable: a catalogue is
    # reset regularly and a product may be deleted. The snapshot below is
    # what the dashboard displays.
    product = models.ForeignKey(
        StoreProduct, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="order_items",
    )
    product_title = models.CharField(max_length=255)
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(
        max_digits=10, decimal_places=3, validators=[MinValueValidator(0)],
        help_text="Price charged to the customer, in TND.",
    )
    unit_cost = models.DecimalField(
        max_digits=10, decimal_places=3, default=0, validators=[MinValueValidator(0)],
        help_text="Original supplier cost of one unit, in the source currency.",
    )
    currency = models.CharField(max_length=8, default="TND", help_text="Currency of unit_cost.")
    currency_rate = models.DecimalField(
        max_digits=12, decimal_places=6, default=1, validators=[MinValueValidator(0)],
        help_text="Rate applied to unit_cost to reach TND.",
    )
    supplier_name = models.CharField(
        max_length=100, blank=True, help_text="Supplier name at the time of the order."
    )
    source_url = models.CharField(
        max_length=500, blank=True, help_text="Supplier product URL at the time of the order."
    )
    image_url = models.CharField(max_length=500, blank=True, help_text="Product image URL.")
    compare_at_price = models.DecimalField(
        max_digits=10, decimal_places=3, default=0, validators=[MinValueValidator(0)],
        help_text="Supplier reference price before discount (0 = no reference).",
    )

    def line_total(self):
        return self.unit_price * self.quantity

    @property
    def supplier_display(self):
        """Human readable supplier name.

        ``supplier_name`` is the raw scraper source key (e.g.
        ``tunisianet_ordinateurs_portables``). The operator reads a brand
        name, not a source key.
        """
        raw = (self.supplier_name or "").strip()
        if not raw:
            return "Fournisseur inconnu"
        prefix = raw.split("_")[0].lower()
        return SUPPLIER_BRANDS.get(prefix, raw.replace("_", " ").title())

    def line_cost_tnd(self):
        """Supplier cost of the line, converted to TND."""
        return (self.unit_cost * self.currency_rate * self.quantity).quantize(Decimal("0.001"))

    def line_margin(self):
        """Gross margin of the line, in TND."""
        return self.line_total() - self.line_cost_tnd()

    def __str__(self):
        return f"{self.quantity}x {self.product_title}"


class OrderEvent(models.Model):
    """History of the status changes of an order (the tracking trail)."""

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="events")
    from_status = models.CharField(max_length=30, blank=True)
    to_status = models.CharField(max_length=30)
    note = models.TextField(blank=True)
    created_by = models.CharField(max_length=150, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Order {self.order_id}: {self.from_status or 'NEW'} -> {self.to_status}"

    @staticmethod
    def status_label(value):
        """Human label of a status constant (Order.STATUS_CHOICES)."""
        for code, label in Order.STATUS_CHOICES:
            if code == value:
                return label
        return value or "—"

    @property
    def from_status_label(self):
        return self.status_label(self.from_status)

    @property
    def to_status_label(self):
        return self.status_label(self.to_status)


class Delivery(models.Model):
    order = models.OneToOneField(Order, on_delete=models.CASCADE, related_name="delivery")
    tracking_number = models.CharField(max_length=100, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    paid_on_delivery = models.BooleanField(default=False)
    returned_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Delivery for Order {self.order.id}"


class Cart(models.Model):
    session_key = models.CharField(max_length=40, db_index=True)
    # The tenant product in the cart. A visitor never buys a product that
    # belongs to another store.
    product = models.ForeignKey(StoreProduct, on_delete=models.CASCADE)
    # The store the cart belongs to, so a sub-store cart never mixes with
    # the flagship catalogue.
    store = models.ForeignKey(
        Store, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="carts",
    )
    quantity = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("session_key", "product")]
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.quantity}x {self.product.title} ({self.session_key[:8]})"
