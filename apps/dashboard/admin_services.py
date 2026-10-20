"""Analytics for the platform superadmin.

All the aggregates here are platform-wide. The vendor counterpart lives
in apps.dashboard.services and is scoped to a single store.
"""
from datetime import timedelta
from decimal import Decimal

from django.db.models import Count, Q, Sum
from django.db.models.functions import TruncDay
from django.utils import timezone

from apps.orders.models import Order


def platform_analytics():
    """GMV, margins, delivery rate, return rate and the chart data."""
    now = timezone.now()
    today = now.date()
    month_ago = today - timedelta(days=30)

    orders_qs = Order.objects.all()

    gmv_today = orders_qs.filter(created_at__date=today).aggregate(
        total=Sum("total_amount")
    )["total"] or Decimal("0")
    gmv_mtd = orders_qs.filter(created_at__date__gte=month_ago).aggregate(
        total=Sum("total_amount")
    )["total"] or Decimal("0")
    total_cost = orders_qs.aggregate(total=Sum("total_cost"))["total"] or Decimal("0")
    total_revenue = orders_qs.aggregate(total=Sum("total_amount"))["total"] or Decimal("0")

    total_orders = orders_qs.count()
    delivered = orders_qs.filter(status=Order.STATUS_DELIVERED_AND_PAID).count()
    returned = orders_qs.filter(status=Order.STATUS_RETURNED).count()
    shipped = orders_qs.filter(
        status__in=[Order.STATUS_SHIPPED, Order.STATUS_DELIVERED_AND_PAID]
    ).count()

    delivery_rate = round((delivered / total_orders) * 100, 2) if total_orders else 0
    return_rate = round((returned / total_orders) * 100, 2) if total_orders else 0
    fulfilment_rate = round((shipped / total_orders) * 100, 2) if total_orders else 0

    gross_margin = total_revenue - total_cost
    margin_percent = (
        round((gross_margin / total_revenue) * 100, 2) if total_revenue else 0
    )

    # Daily revenue vs supplier COGS, for the area chart.
    revenue_by_day = list(
        orders_qs.filter(created_at__date__gte=today - timedelta(days=14))
        .annotate(day=TruncDay("created_at"))
        .values("day")
        .annotate(
            revenue=Sum("total_amount"),
            cogs=Sum("total_cost"),
            orders=Count("id"),
        )
        .order_by("day")
    )

    # Orders by Tunisian governorate, for the bar chart.
    by_governorate = list(
        orders_qs.values("customer__governorate")
        .annotate(count=Count("id"), revenue=Sum("total_amount"))
        .order_by("-count")
    )

    # COD fulfilment funnel.
    funnel = [
        {"stage": "Pending", "count": orders_qs.filter(
            status=Order.STATUS_PENDING_CONFIRMATION).count()},
        {"stage": "Confirmed", "count": orders_qs.filter(
            status=Order.STATUS_CONFIRMED).count()},
        {"stage": "Ordered", "count": orders_qs.filter(
            status=Order.STATUS_ORDERED_FROM_SUPPLIER).count()},
        {"stage": "Shipped", "count": orders_qs.filter(
            status=Order.STATUS_SHIPPED).count()},
        {"stage": "Paid", "count": delivered},
        {"stage": "Returned", "count": returned},
    ]

    # Top products by revenue, platform-wide.
    top_products = list(
        OrderItem.objects.values("product_title")
        .annotate(
            revenue=Sum("unit_price"),
            units=Count("id"),
        )
        .order_by("-revenue")[:10]
    )

    return {
        "gmv_today": gmv_today,
        "gmv_mtd": gmv_mtd,
        "total_revenue": total_revenue,
        "total_cost": total_cost,
        "gross_margin": gross_margin,
        "margin_percent": margin_percent,
        "total_orders": total_orders,
        "delivered_orders": delivered,
        "returned_orders": returned,
        "delivery_rate": delivery_rate,
        "return_rate": return_rate,
        "fulfilment_rate": fulfilment_rate,
        "revenue_by_day": revenue_by_day,
        "by_governorate": by_governorate,
        "funnel": funnel,
        "top_products": top_products,
    }
