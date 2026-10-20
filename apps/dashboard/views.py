"""Dashboard views: executive analytics + order command centre.

The dashboard is the vendor control panel: it shows the data of the
tenant resolved by the middleware. A staff account without a store of
its own operates on the flagship.
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.db.models import Sum, Count, Q, Avg
from django.db.models.functions import TruncDay
from django.utils import timezone
from django.http import JsonResponse
from datetime import timedelta

from apps.catalog.models import StoreProduct
from apps.orders.models import Order, OrderItem, Delivery, OrderEvent
from apps.scraper.models import ScraperLog
from apps.dashboard.services import financial_unit_economics, delivery_kpis
from apps.orders.services import change_order_status


def _is_staff(user):
    """The dashboard exposes revenue KPIs: restrict it to staff accounts."""
    return user.is_active and user.is_staff


staff_required = user_passes_test(_is_staff)


def _tenant_store(request):
    """The store the dashboard belongs to (the flagship by default)."""
    return getattr(request, "tenant_store", None)


def _scoped(queryset, request, field="store"):
    """Restrict a queryset to the tenant of the request.

    A vendor only ever sees its own rows. A staff account working on the
    flagship sees the whole platform.
    """
    store = _tenant_store(request)
    if store is None or store.is_platform_default:
        return queryset
    return queryset.filter(**{field: store})


@login_required
@staff_required
def overview(request):
    now = timezone.now()
    today = now.date()
    week_ago = today - timedelta(days=7)
    month_ago = today - timedelta(days=30)

    store = _tenant_store(request)

    # KPI Cards: the catalogue of the tenant, not the central pool.
    products = _scoped(StoreProduct.objects.all(), request)
    total_products = products.count()
    active_products = products.filter(is_published=True, in_stock=True).count()

    orders = _scoped(Order.objects.all(), request)
    total_orders = orders.count()

    # Financial KPIs
    gmv_today = orders.filter(created_at__date=today).aggregate(total=Sum("total_amount"))["total"] or 0
    gmv_7d = orders.filter(created_at__date__gte=week_ago).aggregate(total=Sum("total_amount"))["total"] or 0
    gmv_mtd = orders.filter(created_at__date__gte=month_ago).aggregate(total=Sum("total_amount"))["total"] or 0

    # Delivery KPIs
    deliv = delivery_kpis()

    # Pending confirmations (action items)
    pending_confirmations = orders.filter(status=Order.STATUS_PENDING_CONFIRMATION).count()

    # Recent scraper logs
    recent_logs = ScraperLog.objects.order_by("-started_at")[:5]

    # Chart data: GMV by day (last 7 days)
    gmv_by_day = (
        orders.filter(created_at__date__gte=week_ago)
        .annotate(day=TruncDay("created_at"))
        .values("day")
        .annotate(total=Sum("total_amount"), count=Count("id"))
        .order_by("day")
    )

    # Chart data: orders by status
    orders_by_status = (
        orders.values("status")
        .annotate(count=Count("id"), revenue=Sum("total_amount"))
        .order_by("-count")
    )

    # Top products by revenue
    top_products = (
        products.filter(is_published=True)
        .order_by("-selling_price")[:5]
    )

    # Command centre: the orders waiting for a phone confirmation.
    action_orders = (
        orders.filter(status=Order.STATUS_PENDING_CONFIRMATION)
        .select_related("customer")
        .prefetch_related("items")[:10]
    )

    # Margin snapshot: what the business actually earns per order.
    margin_stats = orders.aggregate(
        revenue=Sum("total_amount"),
        cost=Sum("total_cost"),
        avg_margin=Avg("total_amount"),
    )

    return render(request, "dashboard/overview.html", {
        "store": store,
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
        "action_orders": action_orders,
        "total_revenue": margin_stats["revenue"] or 0,
        "total_cost": margin_stats["cost"] or 0,
        "gross_margin": (margin_stats["revenue"] or 0) - (margin_stats["cost"] or 0),
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
    """Command centre: the list of orders, filterable by status."""
    status = (request.GET.get("status") or "").strip()
    query = (request.GET.get("q") or "").strip()

    orders = _scoped(
        Order.objects.select_related("customer").prefetch_related("items"), request
    )

    if status:
        orders = orders.filter(status=status)
    if query:
        orders = orders.filter(
            Q(customer__full_name__icontains=query)
            | Q(customer__phone__icontains=query)
            | Q(id__exact=query if query.isdigit() else 0)
        )

    orders = orders[:100]

    # Counts per status, for the filter pills.
    counts = {
        row["status"]: row["count"]
        for row in _scoped(Order.objects.all(), request)
        .values("status")
        .annotate(count=Count("id"))
    }
    counts["ALL"] = sum(counts.values())

    return render(
        request,
        "dashboard/orders.html",
        {
            "orders": orders,
            "status": status,
            "q": query,
            "status_choices": Order.STATUS_CHOICES,
            "status_counts": counts,
        },
    )


@login_required
@staff_required
def order_detail(request, order_id):
    """Full command sheet of one order.

    Shows the client details (name, phone, address), every line with its
    supplier, its original cost and the price charged, and the tracking
    trail of the status changes.
    """
    order = get_object_or_404(
        _scoped(
            Order.objects.select_related("customer").prefetch_related(
                "items", "events"
            ),
            request,
        ),
        pk=order_id,
    )
    items = list(order.items.all())
    suppliers = sorted({item.supplier_name for item in items if item.supplier_name})
    total_cost = sum((item.line_cost_tnd() for item in items), order.total_cost * 0)

    return render(
        request,
        "dashboard/order_detail.html",
        {
            "order": order,
            "items": items,
            "suppliers": suppliers,
            "item_count": sum(item.quantity for item in items),
            "total_cost": total_cost,
            "margin": order.total_amount - total_cost,
            "margin_percent": order.margin_percent,
            "status_choices": Order.STATUS_CHOICES,
            "events": order.events.all(),
        },
    )


@login_required
@staff_required
def order_update_status(request, order_id):
    """Move an order to a new status (HTMX, from the command sheet)."""
    order = get_object_or_404(_scoped(Order.objects.all(), request), pk=order_id)
    new_status = (request.POST.get("status") or "").strip()
    note = (request.POST.get("note") or "").strip()

    try:
        change_order_status(order, new_status, note=note, user=request.user)
    except ValueError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, f"Commande #{order.id}: {order.get_status_display()}.")

    return redirect("dashboard:order_detail", order_id=order.id)


@login_required
@staff_required
def order_note(request, order_id):
    """Append an internal note to an order (HTMX)."""
    order = get_object_or_404(_scoped(Order.objects.all(), request), pk=order_id)
    note = (request.POST.get("note") or "").strip()
    if note:
        OrderEvent.objects.create(
            order=order,
            from_status=order.status,
            to_status=order.status,
            note=note,
            created_by=request.user.get_username(),
        )
        messages.success(request, "Note ajoutée.")
    return redirect("dashboard:order_detail", order_id=order.id)


@login_required
@staff_required
def order_call(request, order_id):
    """One-click phone confirmation log.

    Records that the operator called the client, without changing the
    order status: the status is changed explicitly from the command sheet.
    """
    order = get_object_or_404(_scoped(Order.objects.all(), request), pk=order_id)
    outcome = (request.POST.get("outcome") or "Appel effectué").strip()
    OrderEvent.objects.create(
        order=order,
        from_status=order.status,
        to_status=order.status,
        note=f"Appel client — {outcome}",
        created_by=request.user.get_username(),
    )
    if order.status == Order.STATUS_PENDING_CONFIRMATION:
        change_order_status(
            order,
            Order.STATUS_CONFIRMED,
            note="Client confirmé par téléphone.",
            user=request.user,
        )
    messages.success(request, f"Commande #{order.id} confirmée.")
    return redirect("dashboard:order_detail", order_id=order.id)
