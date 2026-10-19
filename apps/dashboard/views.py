"""Dashboard views: custom analytics control plane."""
from django.shortcuts import render
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db.models import Sum, Count, Avg
from django.db.models.functions import TruncDay, TruncWeek, TruncMonth
from django.utils import timezone
from datetime import timedelta
from apps.catalog.models import Product
from apps.orders.models import Order, Delivery
from apps.scraper.models import ScraperLog
from apps.dashboard.services import financial_unit_economics, delivery_kpis


def _is_staff(user):
    """The dashboard exposes revenue KPIs: restrict it to staff accounts."""
    return user.is_active and user.is_staff


staff_required = user_passes_test(_is_staff)


@login_required
@staff_required
def overview(request):
    now = timezone.now()
    today = now.date()
    week_ago = today - timedelta(days=7)
    month_ago = today - timedelta(days=30)

    # KPI Cards
    total_products = Product.objects.count()
    active_products = Product.objects.filter(is_active=True).count()
    total_orders = Order.objects.count()

    # Financial KPIs
    gmv_today = Order.objects.filter(created_at__date=today).aggregate(total=Sum("total_amount"))["total"] or 0
    gmv_7d = Order.objects.filter(created_at__date__gte=week_ago).aggregate(total=Sum("total_amount"))["total"] or 0
    gmv_mtd = Order.objects.filter(created_at__date__gte=month_ago).aggregate(total=Sum("total_amount"))["total"] or 0

    # Delivery KPIs
    deliv = delivery_kpis()

    # Pending confirmations (action items)
    pending_confirmations = Order.objects.filter(status=Order.STATUS_PENDING_CONFIRMATION).count()

    # Recent scraper logs
    recent_logs = ScraperLog.objects.order_by("-started_at")[:5]

    # Chart data: GMV by day (last 7 days)
    gmv_by_day = (
        Order.objects.filter(created_at__date__gte=week_ago)
        .annotate(day=TruncDay("created_at"))
        .values("day")
        .annotate(total=Sum("total_amount"), count=Count("id"))
        .order_by("day")
    )

    # Chart data: orders by status
    orders_by_status = (
        Order.objects.values("status")
        .annotate(count=Count("id"), revenue=Sum("total_amount"))
        .order_by("-count")
    )

    # Top products by revenue
    top_products = (
        Product.objects.filter(is_active=True)
        .order_by("-retail_price")[:5]
    )

    return render(request, "dashboard/overview.html", {
        "total_products": total_products,
        "active_products": active_products,
        "total_orders": total_orders,
        "gmv_today": gmv_today,
        "gmv_7d": gmv_7d,
        "gmv_mtd": gmv_mtd,
        "pending_confirmations": pending_confirmations,
        "delivered_pct": deliv["paid_rate"],
        "returned_pct": round((deliv["returned"] / deliv["total"]) * 100, 2) if deliv["total"] else 0,
        "recent_logs": recent_logs,
        "gmv_by_day": list(gmv_by_day),
        "orders_by_status": list(orders_by_status),
        "top_products": top_products,
    })


@login_required
@staff_required
def scrapers(request):
    from apps.scraper.models import ScrapedSource
    sources = ScrapedSource.objects.all()
    logs = ScraperLog.objects.order_by("-started_at")[:20]
    return render(request, "dashboard/scrapers.html", {"sources": sources, "logs": logs})


@login_required
@staff_required
def orders_list(request):
    orders = Order.objects.order_by("-created_at")[:50]
    return render(request, "dashboard/orders.html", {"orders": orders})
