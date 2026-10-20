"""The platform analytics plane.

``/admin-dashboard/analytics/`` is a full operating picture of the
platform, built outside the Django admin so the operator gets a real
console: one page, every tenant, the money, the funnel and the health
of the scraping plane.

The aggregates are computed here rather than in the views so they can
be unit-tested and reused (the CSV export, the tests).
"""
from datetime import timedelta
from decimal import Decimal

from django.db.models import Count, F, Q, Sum
from django.db.models.functions import TruncDay
from django.utils import timezone

from apps.catalog.models import Product, Store, StoreProduct
from apps.orders.models import Order, OrderItem, PayoutSettlement
from apps.scraper.models import ScrapedSource, ScraperLog

from apps.orders.finance import DELIVERED_STATUS, delivered_orders

ZERO = Decimal("0.000")


def _pct(part, whole):
    """A percentage, rounded to two decimals, safe on a zero denominator."""
    if not whole:
        return Decimal("0.00")
    return (Decimal(part) / Decimal(whole) * Decimal("100")).quantize(
        Decimal("0.01")
    )


def platform_kpis():
    """The headline numbers of the platform."""
    orders_qs = Order.objects.all()
    today = timezone.now().date()

    total_orders = orders_qs.count()
    delivered = orders_qs.filter(status=DELIVERED_STATUS).count()
    returned = orders_qs.filter(status=Order.STATUS_RETURNED).count()
    pending = orders_qs.filter(
        status=Order.STATUS_PENDING_CONFIRMATION
    ).count()

    aggregates = orders_qs.aggregate(
        gmv=Sum("total_amount"),
        cost=Sum("total_cost"),
        courier=Sum("courier_cost"),
        cut=Sum("platform_cut"),
        payout=Sum("vendor_payout"),
    )

    gmv = aggregates["gmv"] or ZERO
    cost = aggregates["cost"] or ZERO
    courier = aggregates["courier"] or ZERO
    cut = aggregates["cut"] or ZERO
    payout = aggregates["payout"] or ZERO

    delivered_aggregates = orders_qs.filter(status=DELIVERED_STATUS).aggregate(
        gmv=Sum("total_amount"),
        cut=Sum("platform_cut"),
    )
    delivered_gmv = delivered_aggregates["gmv"] or ZERO
    delivered_cut = delivered_aggregates["cut"] or ZERO

    unsettled = delivered_orders(unsettled_only=True).aggregate(
        gmv=Sum("total_amount"),
        cut=Sum("platform_cut"),
        payout=Sum("vendor_payout"),
        orders=Count("id"),
    )

    return {
        "total_orders": total_orders,
        "delivered_orders": delivered,
        "returned_orders": returned,
        "pending_orders": pending,
        "gmv": gmv,
        "gmv_today": orders_qs.filter(created_at__date=today).aggregate(
            total=Sum("total_amount")
        )["total"] or ZERO,
        "supplier_cost": cost,
        "courier_cost": courier,
        "gross_margin": gmv - cost,
        "gross_margin_percent": _pct(gmv - cost, gmv),
        "platform_cut": cut,
        "vendor_payout": payout,
        "realized_cut": delivered_cut,
        "realized_cut_percent": _pct(delivered_cut, delivered_gmv),
        "delivery_rate": _pct(delivered, total_orders),
        "return_rate": _pct(returned, total_orders),
        "unsettled_orders": unsettled["orders"] or 0,
        "unsettled_gmv": unsettled["gmv"] or ZERO,
        "unsettled_cut": unsettled["cut"] or ZERO,
        "unsettled_payout": unsettled["payout"] or ZERO,
        "store_count": Store.objects.count(),
        "active_store_count": Store.objects.filter(
            is_active=True, status=Store.STATUS_ACTIVE
        ).count(),
        "central_pool_size": Product.objects.filter(is_active=True).count(),
        "published_products": StoreProduct.objects.filter(
            is_published=True, in_stock=True
        ).count(),
        "scraper_sources": ScrapedSource.objects.count(),
        "active_scraper_sources": ScrapedSource.objects.filter(
            is_active=True
        ).count(),
    }


def store_rows():
    """One line per store: its catalogue, its orders and its money."""
    rows = []
    for store in Store.objects.all():
        products = StoreProduct.objects.filter(store=store)
        published = products.filter(is_published=True, in_stock=True).count()

        orders = Order.objects.filter(store=store)
        totals = orders.aggregate(
            gmv=Sum("total_amount"),
            cost=Sum("total_cost"),
            cut=Sum("platform_cut"),
            payout=Sum("vendor_payout"),
            orders=Count("id"),
        )
        delivered = orders.filter(status=DELIVERED_STATUS).aggregate(
            count=Count("id"),
            cut=Sum("platform_cut"),
        )
        unsettled = delivered_orders(store, unsettled_only=True).aggregate(
            count=Count("id"),
            cut=Sum("platform_cut"),
        )

        gmv = totals["gmv"] or ZERO
        cut = totals["cut"] or ZERO
        delivered_cut = delivered["cut"] or ZERO
        delivered_gmv = orders.filter(status=DELIVERED_STATUS).aggregate(
            total=Sum("total_amount")
        )["total"] or ZERO

        settlements = PayoutSettlement.objects.filter(store=store)
        paid_settlements = settlements.filter(is_paid=True).count()

        rows.append(
            {
                "store": store,
                "storefront_url": store.storefront_url,
                "is_operational": store.is_operational,
                "products": products.count(),
                "published_products": published,
                "orders": totals["orders"] or 0,
                "gmv": gmv,
                "supplier_cost": totals["cost"] or ZERO,
                "gross_margin": gmv - (totals["cost"] or ZERO),
                "platform_cut": cut,
                "vendor_payout": totals["payout"] or ZERO,
                "delivered": delivered["count"] or 0,
                "delivered_cut": delivered_cut,
                "realized_rate": _pct(delivered_cut, delivered_gmv),
                "unsettled_orders": unsettled["count"] or 0,
                "unsettled_cut": unsettled["cut"] or ZERO,
                "settlements": settlements.count(),
                "paid_settlements": paid_settlements,
                "unpaid_settlements": settlements.count() - paid_settlements,
            }
        )

    rows.sort(key=lambda row: row["gmv"], reverse=True)
    return rows


def cod_funnel():
    """The COD funnel, platform-wide, with a conversion rate per step."""
    orders_qs = Order.objects.all()
    stages = [
        ("Pending", Order.STATUS_PENDING_CONFIRMATION),
        ("Confirmed", Order.STATUS_CONFIRMED),
        ("Ordered", Order.STATUS_ORDERED_FROM_SUPPLIER),
        ("Shipped", Order.STATUS_SHIPPED),
        ("Paid", DELIVERED_STATUS),
        ("Returned", Order.STATUS_RETURNED),
    ]

    rows = []
    previous = None
    for label, status in stages:
        count = orders_qs.filter(status=status).count()
        rows.append(
            {
                "stage": label,
                "count": count,
                "share": _pct(count, orders_qs.count()),
                "step_rate": _pct(count, previous) if previous else None,
            }
        )
        # The funnel follows the happy path: the returned orders are a
        # loss, not a step forward.
        if status != Order.STATUS_RETURNED:
            previous = count
    return rows


def revenue_series(days=30):
    """The daily GMV, cost and margin of the platform."""
    since = timezone.now().date() - timedelta(days=days - 1)
    rows = list(
        Order.objects.filter(created_at__date__gte=since)
        .annotate(day=TruncDay("created_at"))
        .values("day")
        .annotate(
            revenue=Sum("total_amount"),
            cogs=Sum("total_cost"),
            cut=Sum("platform_cut"),
            orders=Count("id"),
        )
        .order_by("day")
    )
    for row in rows:
        # The margin is computed here so the template stays readable.
        row["margin"] = (row["revenue"] or ZERO) - (row["cogs"] or ZERO)
    return rows


def governorate_split():
    """The orders per Tunisian governorate."""
    return list(
        Order.objects.values("customer__governorate")
        .annotate(
            count=Count("id"),
            revenue=Sum("total_amount"),
        )
        .order_by("-count")[:12]
    )


def top_products(limit=10):
    """The best sellers of the platform, by revenue."""
    return list(
        OrderItem.objects.values("product_title")
        .annotate(
            revenue=Sum(F("unit_price") * F("quantity")),
            units=Sum("quantity"),
        )
        .order_by("-revenue")[:limit]
    )


def scraper_health():
    """The state of the scraping plane, source by source."""
    sources = []
    for source in ScrapedSource.objects.all():
        last_log = ScraperLog.objects.filter(source=source).order_by(
            "-started_at"
        ).first()
        sources.append(
            {
                "source": source,
                "last_log": last_log,
                "status": last_log.status if last_log else "never",
                "products_found": last_log.products_found if last_log else 0,
                "products_updated": last_log.products_updated if last_log else 0,
                "has_errors": bool(last_log and last_log.errors),
            }
        )
    return sources


def analytics_payload():
    """Everything the analytics page needs, in one bundle."""
    return {
        "kpis": platform_kpis(),
        "stores": store_rows(),
        "funnel": cod_funnel(),
        "revenue": revenue_series(),
        "governorates": governorate_split(),
        "top_products": top_products(),
        "scrapers": scraper_health(),
    }
