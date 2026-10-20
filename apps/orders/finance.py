"""Commission accounting and payout settlement.

The Tunisian dropshipping flow is cash on delivery: the courier
collects the money when the parcel is delivered. The platform fee is
therefore only *realized* on a delivered and paid order — a pending or
returned order generates no commission.

Two levels of aggregation live here:

* :func:`store_ledger` — the per-store breakdown shown to the
  superadmin and to the vendor;
* :func:`build_settlement` — the creation of a payout batch for the
  delivered orders that were not settled yet.
"""
from decimal import Decimal

from django.db import transaction
from django.db.models import Count, F, Q, Sum
from django.utils import timezone

from .models import Order, PayoutSettlement

ZERO = Decimal("0.000")
MILLIME = Decimal("0.001")

#: The status that realizes the platform commission.
DELIVERED_STATUS = Order.STATUS_DELIVERED_AND_PAID


def delivered_orders(store=None, *, unsettled_only=False, since=None, until=None):
    """The delivered and paid orders of the platform or of one store."""
    queryset = Order.objects.filter(status=DELIVERED_STATUS)
    if store is not None:
        queryset = queryset.filter(store=store)
    if unsettled_only:
        queryset = queryset.filter(is_settled=False)
    if since is not None:
        queryset = queryset.filter(created_at__gte=since)
    if until is not None:
        queryset = queryset.filter(created_at__lte=until)
    return queryset


def platform_financials(store=None, *, since=None, until=None):
    """The KPI block of the financial ledger.

    Returns the realized commission (delivered orders only), the
    unsettled balance, the average commission per delivered order and
    the gross merchandise value.
    """
    queryset = delivered_orders(store, since=since, until=until)

    aggregates = queryset.aggregate(
        gmv=Sum("total_amount"),
        supplier_cost=Sum("total_cost"),
        courier_cost=Sum("courier_cost"),
        platform_cut=Sum("platform_cut"),
        vendor_payout=Sum("vendor_payout"),
        orders=Count("id"),
    )

    unsettled = delivered_orders(store, unsettled_only=True).aggregate(
        gmv=Sum("total_amount"),
        platform_cut=Sum("platform_cut"),
        vendor_payout=Sum("vendor_payout"),
        orders=Count("id"),
    )

    gmv = aggregates["gmv"] or ZERO
    platform_cut = aggregates["platform_cut"] or ZERO
    orders = aggregates["orders"] or 0

    average_commission = (
        (platform_cut / orders).quantize(MILLIME) if orders else ZERO
    )

    # The COD money still on the road: the orders that were shipped or
    # confirmed but not delivered yet. The commission is not realized
    # on them, but the platform is carrying the risk.
    in_flight = Order.objects.filter(
        status__in=[
            Order.STATUS_CONFIRMED,
            Order.STATUS_ORDERED_FROM_SUPPLIER,
            Order.STATUS_SHIPPED,
        ]
    )
    if store is not None:
        in_flight = in_flight.filter(store=store)
    in_flight_totals = in_flight.aggregate(
        gmv=Sum("total_amount"), orders=Count("id")
    )

    return {
        "gmv": gmv,
        "supplier_cost": aggregates["supplier_cost"] or ZERO,
        "courier_cost": aggregates["courier_cost"] or ZERO,
        "platform_cut": platform_cut,
        "vendor_payout": aggregates["vendor_payout"] or ZERO,
        "delivered_orders": orders,
        "average_commission": average_commission,
        "unsettled_orders": unsettled["orders"] or 0,
        "unsettled_gmv": unsettled["gmv"] or ZERO,
        "unsettled_platform_cut": unsettled["platform_cut"] or ZERO,
        "unsettled_vendor_payout": unsettled["vendor_payout"] or ZERO,
        "in_flight_orders": in_flight_totals["orders"] or 0,
        "in_flight_gmv": in_flight_totals["gmv"] or ZERO,
    }


def store_ledger(store, *, since=None, until=None):
    """The financial breakdown of one store.

    Everything the vendor sees on its finances page, and everything the
    superadmin sees in the per-store ledger of the console.
    """
    financials = platform_financials(store, since=since, until=until)

    totals = Order.objects.filter(store=store).aggregate(
        gmv=Sum("total_amount"),
        supplier_cost=Sum("total_cost"),
        orders=Count("id"),
    )

    by_status = list(
        Order.objects.filter(store=store)
        .values("status")
        .annotate(count=Count("id"), revenue=Sum("total_amount"))
        .order_by("-count")
    )

    settlements = list(
        PayoutSettlement.objects.filter(store=store).order_by("-created_at")[:20]
    )

    return {
        "store": store,
        "total_orders": totals["orders"] or 0,
        "total_gmv": totals["gmv"] or ZERO,
        "supplier_cost": totals["supplier_cost"] or ZERO,
        "by_status": by_status,
        "settlements": settlements,
        **financials,
    }


def platform_ledger(*, since=None, until=None):
    """The platform-wide financial breakdown, per store."""
    financials = platform_financials(since=since, until=until)
    financials["by_store"] = per_store_ledger(since=since, until=until)
    return financials


def per_store_ledger(*, since=None, until=None):
    """One ledger line per store that has orders."""
    rows = (
        Order.objects.values("store_id", "store__name", "store__slug")
        .annotate(
            orders=Count("id"),
            gmv=Sum("total_amount"),
            supplier_cost=Sum("total_cost"),
            delivered=Count(
                "id", filter=Q(status=DELIVERED_STATUS)
            ),
            platform_cut=Sum(
                "platform_cut", filter=Q(status=DELIVERED_STATUS)
            ),
            vendor_payout=Sum(
                "vendor_payout", filter=Q(status=DELIVERED_STATUS)
            ),
        )
        .order_by("-gmv")
    )

    results = []
    for row in rows:
        gmv = row["gmv"] or ZERO
        results.append(
            {
                "store_id": row["store_id"],
                "store_name": row["store__name"] or "—",
                "store_slug": row["store__slug"] or "",
                "orders": row["orders"] or 0,
                "gmv": gmv,
                "supplier_cost": row["supplier_cost"] or ZERO,
                "delivered": row["delivered"] or 0,
                "platform_cut": row["platform_cut"] or ZERO,
                "vendor_payout": row["vendor_payout"] or ZERO,
                "realized_rate": (
                    (row["platform_cut"] / gmv * Decimal("100")).quantize(
                        Decimal("0.01")
                    )
                    if gmv
                    else Decimal("0.00")
                ),
            }
        )
    return results


@transaction.atomic
def build_settlement(store, *, payout_method="Virement Bancaire / D17", reference=None):
    """Create the payout batch of the delivered orders of a store.

    Only the orders that are delivered, paid and not yet settled are
    taken. The batch keeps the totals of the platform cut and of the net
    payout, and every order of the batch is attached to it.

    Returns the settlement, or ``None`` when there is nothing to pay.
    """
    # Only the orders that are not attached to a batch yet: an order
    # waiting for its disbursement is already in a batch, it must not be
    # paid twice.
    orders = list(
        delivered_orders(store, unsettled_only=True)
        .filter(settlement_batch__isnull=True)
        .select_related("store")
        .order_by("created_at")
    )
    if not orders:
        return None

    # The commission is (re)computed at the moment of the settlement:
    # the rate of the store may have changed since the delivery, and
    # the ledger must reflect the current rule.
    for order in orders:
        order.calculate_commissions(save=True)

    gmv = sum((order.total_amount for order in orders), ZERO)
    platform_cut = sum((order.platform_cut for order in orders), ZERO)
    vendor_payout = sum((order.vendor_payout for order in orders), ZERO)

    settlement = PayoutSettlement.objects.create(
        store=store,
        reference=reference or _next_reference(store),
        total_delivered_orders=len(orders),
        total_gmv=gmv.quantize(MILLIME),
        total_platform_cut=platform_cut.quantize(MILLIME),
        net_payout_to_vendor=vendor_payout.quantize(MILLIME),
        payout_method=payout_method,
    )

    Order.objects.filter(pk__in=[order.pk for order in orders]).update(
        settlement_batch=settlement
    )
    return settlement


def _next_reference(store):
    """A unique, readable reference for a payout batch."""
    stamp = timezone.now().strftime("%Y%m%d")
    base = f"PAY-{stamp}-{store.slug[:12].upper()}"
    reference = base
    index = 2
    while PayoutSettlement.objects.filter(reference=reference).exists():
        reference = f"{base}-{index}"
        index += 1
    return reference


def settlement_rows(store, *, since=None, until=None):
    """The order lines of the ledger, for the CSV export."""
    queryset = delivered_orders(store, since=since, until=until).select_related(
        "store", "customer"
    )
    rows = []
    for order in queryset:
        rows.append(
            {
                "order_id": order.id,
                "date": order.created_at.strftime("%Y-%m-%d"),
                "store": order.store.name if order.store else "",
                "customer": order.customer.full_name,
                "gross_total": f"{order.total_amount:.3f}",
                "supplier_cost": f"{order.total_cost:.3f}",
                "courier_cost": f"{order.courier_cost:.3f}",
                "platform_cut": f"{order.platform_cut:.3f}",
                "vendor_payout": f"{order.vendor_payout:.3f}",
                "settled": "oui" if order.is_settled else "non",
                "settlement": order.settlement_batch.reference
                if order.settlement_batch
                else "",
            }
        )
    return rows
