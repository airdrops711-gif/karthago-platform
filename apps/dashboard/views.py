"""Dashboard views: custom analytics control plane."""
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from apps.catalog.models import Product
from apps.orders.models import Order
from apps.scraper.models import ScraperLog


@login_required
def overview(request):
    total_products = Product.objects.count()
    active_products = Product.objects.filter(is_active=True).count()
    total_orders = Order.objects.count()
    recent_logs = ScraperLog.objects.order_by("-started_at")[:5]
    return render(request, "dashboard/overview.html", {
        "total_products": total_products,
        "active_products": active_products,
        "total_orders": total_orders,
        "recent_logs": recent_logs,
    })


@login_required
def scrapers(request):
    from apps.scraper.models import ScrapedSource
    sources = ScrapedSource.objects.all()
    logs = ScraperLog.objects.order_by("-started_at")[:20]
    return render(request, "dashboard/scrapers.html", {"sources": sources, "logs": logs})


@login_required
def orders_list(request):
    orders = Order.objects.order_by("-created_at")[:50]
    return render(request, "dashboard/orders.html", {"orders": orders})
