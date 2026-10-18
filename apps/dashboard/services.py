"""Dashboard services: financial unit economics & delivery KPI aggregations."""
from django.db.models import Sum, Count
from apps.orders.models import Order, Delivery


def financial_unit_economics():
    """Aggregate revenue and order counts by status."""
    return Order.objects.values("status").annotate(
        count=Count("id"),
        revenue=Sum("total_amount"),
    )


def delivery_kpis():
    """Delivery KPIs: delivered vs returned, COD paid rate."""
    total = Delivery.objects.count()
    delivered = Delivery.objects.filter(delivered_at__isnull=False).count()
    paid = Delivery.objects.filter(paid_on_delivery=True).count()
    returned = Delivery.objects.filter(returned_at__isnull=False).count()
    return {
        "total": total,
        "delivered": delivered,
        "paid": paid,
        "returned": returned,
        "paid_rate": round((paid / total) * 100, 2) if total else 0,
    }
