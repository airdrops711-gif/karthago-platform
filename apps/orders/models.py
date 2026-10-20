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

    class Meta:
        verbose_name = "Client"
        verbose_name_plural = "Clients"


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

    # --- COD commission accounting -------------------------------------
    # In the Tunisian cash-on-delivery flow the platform fee is only
    # realized when the order is actually delivered and paid. The cut
    # and the vendor share are therefore computed at the delivery, and
    # they stay at zero for every other status (pending, returned,
    # cancelled...).
    courier_cost = models.DecimalField(
        max_digits=10, decimal_places=3, default=Decimal("7.000"),
        validators=[MinValueValidator(0)],
        help_text="Delivery fee paid to the courier, in TND.",
    )
    platform_cut = models.DecimalField(
        max_digits=10, decimal_places=3, default=Decimal("0.000"),
        help_text="Platform commission realized on this order, in TND.",
    )
    vendor_payout = models.DecimalField(
        max_digits=10, decimal_places=3, default=Decimal("0.000"),
        help_text="Net amount owed to the vendor for this order, in TND.",
    )
    is_settled = models.BooleanField(
        default=False,
        help_text="True once the payout has been disbursed to the vendor.",
    )
    settlement_batch = models.ForeignKey(
        "PayoutSettlement", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="orders",
    )

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Commande"
        verbose_name_plural = "Commandes"

    def __str__(self):
        return f"Order {self.id} - {self.customer.full_name}"

    # -- money aliases --------------------------------------------------
    @property
    def gross_total(self):
        """Total charged to the customer, in TND."""
        return self.total_amount

    @property
    def supplier_cost(self):
        """Total supplier cost of the items, in TND."""
        return self.total_cost

    @property
    def is_delivered(self):
        """True when the order reached the paid-delivery state."""
        return self.status == self.STATUS_DELIVERED_AND_PAID

    def calculate_commissions(self, *, save=True):
        """Compute the platform cut and the vendor payout of the order.

        The platform fee is only realized on a delivered and paid order:
        every other status (pending, confirmed, shipped, returned) keeps
        the cut and the payout at zero, because the money was never
        collected.

        The vendor share is the gross amount minus the supplier cost,
        the courier fee and the platform commission. It never goes
        negative: a loss stays a loss, it is not turned into a debt for
        the vendor.
        """
        store = self.store
        if store is None or not self.is_delivered:
            self.platform_cut = Decimal("0.000")
            self.vendor_payout = Decimal("0.000")
        else:
            gross = self.total_amount or Decimal("0.000")
            cut = Decimal("0.000")
            if store.commission_type == store.COMMISSION_TYPE_PERCENT:
                cut = gross * (store.commission_rate / Decimal("100"))
            elif store.commission_type == store.COMMISSION_TYPE_FLAT:
                cut = store.flat_fee_per_order
            elif store.commission_type == store.COMMISSION_TYPE_HYBRID:
                cut = (
                    gross * (store.commission_rate / Decimal("100"))
                ) + store.flat_fee_per_order

            self.platform_cut = cut.quantize(Decimal("0.001"))
            deductions = (
                (self.total_cost or Decimal("0.000"))
                + (self.courier_cost or Decimal("0.000"))
                + self.platform_cut
            )
            self.vendor_payout = max(
                Decimal("0.000"), (gross - deductions).quantize(Decimal("0.001"))
            )

        if save:
            self.save(
                update_fields=[
                    "platform_cut",
                    "vendor_payout",
                    "updated_at",
                ]
            )
        return self.platform_cut, self.vendor_payout

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

    class Meta:
        verbose_name = "Ligne de commande"
        verbose_name_plural = "Lignes de commande"


class PayoutSettlement(models.Model):
    """A batch payout of the platform fees owed to one vendor.

    The COD money is collected by the courier on delivery, so the
    platform fee is only real once the order is delivered and paid. The
    settlement groups the delivered orders of a vendor into a single
    disbursement the operator can mark as paid.
    """

    store = models.ForeignKey(
        Store, on_delete=models.CASCADE, related_name="settlements"
    )
    reference = models.CharField(max_length=64, unique=True)
    total_delivered_orders = models.PositiveIntegerField(default=0)
    total_gmv = models.DecimalField(
        max_digits=10, decimal_places=3, default=Decimal("0.000"),
    )
    total_platform_cut = models.DecimalField(
        max_digits=10, decimal_places=3, default=Decimal("0.000"),
    )
    net_payout_to_vendor = models.DecimalField(
        max_digits=10, decimal_places=3, default=Decimal("0.000"),
    )
    payout_method = models.CharField(
        max_length=50, default="Virement Bancaire / D17",
    )
    is_paid = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Règlement de paiement"
        verbose_name_plural = "Règlements de paiement"

    def __str__(self):
        return f"{self.reference} — {self.store.name} ({self.net_payout_to_vendor} DT)"

    def mark_paid(self):
        """Flag the batch as disbursed and settle its orders."""
        from django.utils import timezone

        self.is_paid = True
        self.paid_at = timezone.now()
        self.save(update_fields=["is_paid", "paid_at"])
        self.orders.filter(is_settled=False).update(
            is_settled=True, settlement_batch=self
        )
        return self


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
        verbose_name = "Événement de commande"
        verbose_name_plural = "Événements de commande"

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

    class Meta:
        verbose_name = "Livraison"
        verbose_name_plural = "Livraisons"


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
        verbose_name = "Panier"
        verbose_name_plural = "Paniers"

    def __str__(self):
        return f"{self.quantity}x {self.product.title} ({self.session_key[:8]})"
