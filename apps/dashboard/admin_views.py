"""Platform superadmin control plane.

``/admin-dashboard/`` is the platform-wide view: every store, every
order, the curation of the flagship homepage and the scraper registry.

The vendor counterpart is ``/dashboard/`` (see apps.dashboard), which is
strictly scoped to the store owned by the signed-in user.
"""
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db.models import Count, Max, Q, Sum
from django.db.models.functions import TruncDay
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from datetime import timedelta

from apps.catalog.models import Product, Store, StoreProduct
from apps.catalog.tenancy import central_pool
from apps.orders.models import Order, OrderItem
from apps.scraper.models import ScrapedSource, ScraperLog

from .admin_services import platform_analytics


def _is_staff(user):
    return user.is_active and user.is_staff


staff_required = user_passes_test(_is_staff)


@login_required
@staff_required
def overview(request):
    """Platform-wide analytics: GMV, margins, delivery and return rates."""
    analytics = platform_analytics()
    context = {
        "stores": Store.objects.all(),
        "store_count": Store.objects.count(),
        "central_pool_size": Product.objects.filter(is_active=True).count(),
        "scraper_sources": ScrapedSource.objects.count(),
        **analytics,
    }
    return render(request, "admin_dashboard/overview.html", context)


@login_required
@staff_required
def stores(request):
    """Registry of every tenant of the platform."""
    stores = Store.objects.annotate(
        product_count=Count("store_products", distinct=True),
        published_count=Count(
            "store_products",
            filter=Q(store_products__is_published=True),
            distinct=True,
        ),
    )
    return render(request, "admin_dashboard/stores.html", {"stores": stores})


@login_required
@staff_required
def curation(request):
    """Cross-store curation: browse every product of every store.

    The superadmin searches the whole platform, then flags the products
    worth showing on the flagship homepage.
    """
    query = (request.GET.get("q") or "").strip()
    store_id = request.GET.get("store") or ""
    only_featured = request.GET.get("featured") == "1"

    products = StoreProduct.objects.select_related("store", "scraped_source_product")

    if query:
        products = products.filter(
            Q(title__icontains=query) | Q(description__icontains=query)
        )
    if store_id.isdigit():
        products = products.filter(store_id=int(store_id))
    if only_featured:
        products = products.filter(is_featured_on_main=True)

    products = products.order_by(
        "-is_featured_on_main", "-featured_priority", "-created_at"
    )[:200]

    context = {
        "products": products,
        "stores": Store.objects.all(),
        "q": query,
        "store_id": store_id,
        "only_featured": only_featured,
        "featured_count": StoreProduct.objects.filter(is_featured_on_main=True).count(),
    }
    return render(request, "admin_dashboard/curation.html", context)


@login_required
@staff_required
def curation_toggle(request, product_id):
    """HTMX one-click toggle of the "featured on main" flag."""
    product = get_object_or_404(StoreProduct, pk=product_id)
    product.is_featured_on_main = not product.is_featured_on_main
    product.featured_curated_at = timezone.now() if product.is_featured_on_main else None
    if product.is_featured_on_main and not product.featured_priority:
        # A newly featured product goes to the top of the showcase.
        highest = (
            StoreProduct.objects.filter(is_featured_on_main=True)
            .aggregate(top=Max("featured_priority"))
        )["top"] or 0
        product.featured_priority = highest + 1
    product.save(update_fields=[
        "is_featured_on_main", "featured_priority", "featured_curated_at", "updated_at",
    ])
    return render(
        request,
        "admin_dashboard/partials/_feature_toggle.html",
        {"product": product},
    )


@login_required
@staff_required
def curation_priority(request, product_id):
    """Set the slot order of a featured product."""
    product = get_object_or_404(StoreProduct, pk=product_id)
    try:
        priority = int(request.POST.get("featured_priority", 0))
    except (TypeError, ValueError):
        priority = 0
    product.featured_priority = max(0, priority)
    product.save(update_fields=["featured_priority", "updated_at"])
    return render(
        request,
        "admin_dashboard/partials/_feature_toggle.html",
        {"product": product},
    )


@login_required
@staff_required
def orders(request):
    """Every order of the platform, across all stores."""
    query = (request.GET.get("q") or "").strip()
    status = (request.GET.get("status") or "").strip()

    orders_qs = Order.objects.select_related("customer")

    if query:
        orders_qs = orders_qs.filter(
            Q(customer__full_name__icontains=query)
            | Q(customer__phone__icontains=query)
        )
    if status:
        orders_qs = orders_qs.filter(status=status)

    orders_qs = orders_qs[:200]

    counts = {
        row["status"]: row["count"]
        for row in Order.objects.values("status").annotate(count=Count("id"))
    }
    counts["ALL"] = sum(counts.values())

    context = {
        "orders": orders_qs,
        "q": query,
        "status": status,
        "status_choices": Order.STATUS_CHOICES,
        "status_counts": counts,
    }
    return render(request, "admin_dashboard/orders.html", context)


@login_required
@staff_required
def scrapers(request):
    """Target site registry + sync logs, platform-wide."""
    sources = ScrapedSource.objects.all()
    logs = ScraperLog.objects.select_related("source").order_by("-started_at")[:30]
    return render(
        request,
        "admin_dashboard/scrapers.html",
        {"sources": sources, "logs": logs},
    )


@login_required
@staff_required
def scraper_run(request, source_id):
    """Trigger a manual scrape of one source (HTMX, with polling).

    The scrape itself is asynchronous: the button starts the Celery task
    and the panel polls the log until the run is finished.
    """
    from apps.scraper.tasks import sync_source

    source = get_object_or_404(ScrapedSource, pk=source_id)
    sync_source.delay(source.id)
    return render(
        request,
        "admin_dashboard/partials/_scraper_run.html",
        {"source": source, "log": None, "started": True},
    )


@login_required
@staff_required
def scraper_status(request, source_id):
    """The state of the last run of a source (HTMX polling target)."""
    source = get_object_or_404(ScrapedSource, pk=source_id)
    log = (
        ScraperLog.objects.filter(source=source)
        .order_by("-started_at")
        .first()
    )
    finished = bool(log and log.finished_at)
    return render(
        request,
        "admin_dashboard/partials/_scraper_run.html",
        {"source": source, "log": log, "started": True, "finished": finished},
    )


@login_required
@staff_required
def selector_sandbox(request):
    """Test CSS selectors against a live URL.

    The superadmin pastes a category URL and a container selector; the
    page returns the number of matches and a JSON preview of the first
    products. It never writes to the database: saving a source is a
    separate, explicit action.
    """
    from apps.scraper.engines import get_engine
    from apps.scraper.utils import normalize_tunisian_price

    url = (request.GET.get("url") or "").strip()
    container = (request.GET.get("container") or "").strip()
    title_sel = (request.GET.get("title") or "").strip()
    price_sel = (request.GET.get("price") or "").strip()

    result = {"url": url, "container": container, "title": title_sel, "price": price_sel}

    if url and container:
        import httpx
        from selectolax.lexbor import LexborHTMLParser as HTMLParser

        try:
            response = httpx.get(
                url, timeout=20, follow_redirects=True,
                headers={"User-Agent": "Mozilla/5.0 (Karthago Selector Sandbox)"},
            )
            tree = HTMLParser(response.text)
            nodes = tree.css(container)
            result["status_code"] = response.status_code
            result["match_count"] = len(nodes)

            samples = []
            for node in nodes[:5]:
                title = ""
                price = ""
                if title_sel:
                    found = node.css_first(title_sel)
                    title = found.text(deep=False, strip=True) if found else ""
                if price_sel:
                    found = node.css_first(price_sel)
                    price = found.text(deep=False, strip=True) if found else ""
                samples.append({
                    "title": title,
                    "price_raw": price,
                    "price": str(normalize_tunisian_price(price)) if price else "",
                })
            result["samples"] = samples
            result["ok"] = True
        except Exception as exc:
            result["ok"] = False
            result["error"] = f"{type(exc).__name__}: {exc}"

    return render(request, "admin_dashboard/selector_sandbox.html", {"result": result})


@login_required
@staff_required
def central_pool_view(request):
    """The central scraped pool, with the import action for the vendors."""
    query = (request.GET.get("q") or "").strip()
    products = central_pool(search=query, limit=200)
    context = {"products": products, "q": query}
    return render(request, "admin_dashboard/central_pool.html", context)
