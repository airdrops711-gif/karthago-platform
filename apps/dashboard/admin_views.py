"""Platform superadmin control plane.

``/admin-dashboard/`` is the platform-wide view: every store, every
order, the curation of the flagship homepage and the scraper registry.

The vendor counterpart is ``/dashboard/`` (see apps.dashboard), which is
strictly scoped to the store owned by the signed-in user.
"""
from decimal import Decimal

import csv

from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db.models import Count, Max, Q, Sum, Value
from django.db.models.functions import Coalesce, TruncDay
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.text import slugify
from datetime import timedelta

from apps.catalog.models import Product, Store, StoreProduct
from apps.catalog.tenancy import central_pool
from apps.orders.models import Order, OrderItem, PayoutSettlement
from apps.scraper.models import ScrapedSource, ScraperLog

from .admin_services import platform_analytics
from . import analytics as analytics_plane


def _date_range(request):
    """The (since, until) date range requested in the query string.

    The dates are parsed as ISO strings and the day boundaries are
    applied, so a range covers the whole day.
    """
    from datetime import datetime, time

    from django.utils import timezone as django_timezone

    def _parse(raw, end_of_day=False):
        if not raw:
            return None
        try:
            parsed = datetime.strptime(raw.strip(), "%Y-%m-%d")
        except ValueError:
            return None
        naive = datetime.combine(parsed.date(), time.max if end_of_day else time.min)
        # The model stores timezone-aware timestamps: a naive boundary
        # would be interpreted in the local time of the server and shift
        # the edges of the period.
        if django_timezone.is_naive(naive):
            return django_timezone.make_aware(naive, django_timezone.get_current_timezone())
        return naive

    return _parse(request.GET.get("since")), _parse(request.GET.get("until"), True)


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
    """Registry of every tenant of the platform.

    The table carries the operational status of each store, its volume
    of products, its delivered orders and the commission the platform
    has realized on it. The lifecycle actions (suspend / reactivate)
    and the commission drawer are posted from this page.
    """
    stores = Store.objects.annotate(
        product_count=Count("store_products", distinct=True),
        published_count=Count(
            "store_products",
            filter=Q(store_products__is_published=True),
            distinct=True,
        ),
        delivered_orders=Count(
            "orders",
            filter=Q(orders__status=Order.STATUS_DELIVERED_AND_PAID),
            distinct=True,
        ),
        total_orders=Count("orders", distinct=True),
        platform_cut=Coalesce(
            Sum(
                "orders__platform_cut",
                filter=Q(orders__status=Order.STATUS_DELIVERED_AND_PAID),
            ),
            Value(Decimal("0.000")),
        ),
        gmv=Coalesce(
            Sum(
                "orders__total_amount",
                filter=Q(orders__status=Order.STATUS_DELIVERED_AND_PAID),
            ),
            Value(Decimal("0.000")),
        ),
    )

    context = {
        "stores": stores,
        "status_choices": Store.STATUS_CHOICES,
        "commission_types": Store.COMMISSION_TYPES,
    }
    return render(request, "admin_dashboard/stores.html", context)


@login_required
@staff_required
def store_toggle_status(request, store_id):
    """Suspend or reactivate a store (HTMX, one click).

    The suspension is immediate and propagates site-wide: the storefront
    of the store answers 404, its products leave the catalogue and the
    homepage showcase, and its documents are evicted from the search
    index. The reason of the suspension is kept and shown to the
    vendor.
    """
    store = get_object_or_404(Store, pk=store_id)

    if store.is_platform_default:
        messages.error(
            request,
            "La boutique flagship ne peut pas être désactivée : elle porte "
            "la racine du site.",
        )
        if request.headers.get("HX-Request"):
            return render(
                request,
                "admin_dashboard/partials/_store_card.html",
                {"store": store},
            )
        return redirect("admin_dashboard:stores")

    if request.method != "POST":
        return redirect("admin_dashboard:stores")

    action = (request.POST.get("action") or "toggle").strip()
    reason = (request.POST.get("deactivation_reason") or "").strip()

    if action == "suspend" or (action == "toggle" and store.is_operational):
        store.suspend(reason)
        messages.success(
            request,
            f"Boutique « {store.name} » suspendue. Ses produits ne sont "
            "plus visibles sur la plateforme.",
        )
    else:
        store.reactivate()
        messages.success(
            request,
            f"Boutique « {store.name} » réactivée. Son catalogue est de "
            "nouveau en ligne.",
        )

    # An HTMX request swaps the card of the store: the operator sees the
    # new state without a full page reload.
    if request.headers.get("HX-Request"):
        store.refresh_from_db()
        return render(
            request,
            "admin_dashboard/partials/_store_card.html",
            {"store": store},
        )

    return redirect("admin_dashboard:stores")


@login_required
@staff_required
def store_commission(request, store_id):
    """Edit the commission rule of a store (HTMX drawer).

    The rule is applied to the next delivered order and to the
    settlements that are not paid yet.
    """
    store = get_object_or_404(Store, pk=store_id)

    if request.method == "POST":
        error = None
        try:
            rate = _parse_decimal(
                request.POST.get("commission_rate"),
                str(store.commission_rate),
            )
            flat = _parse_decimal(
                request.POST.get("flat_fee_per_order"),
                str(store.flat_fee_per_order),
            )
        except ValueError as exc:
            error = str(exc)
            rate, flat = store.commission_rate, store.flat_fee_per_order

        commission_type = (
            request.POST.get("commission_type") or store.commission_type
        ).strip()
        if commission_type not in dict(Store.COMMISSION_TYPES):
            error = "Type de commission inconnu."
            commission_type = store.commission_type

        if error is None:
            if rate < 0 or rate > 100:
                error = "Le taux de commission doit être compris entre 0 et 100."
            elif flat < 0:
                error = "Le frais fixe ne peut pas être négatif."

        if error is None:
            store.commission_type = commission_type
            store.commission_rate = rate
            store.flat_fee_per_order = flat
            store.save(
                update_fields=[
                    "commission_type",
                    "commission_rate",
                    "flat_fee_per_order",
                    "updated_at",
                ]
            )
            messages.success(
                request,
                f"Commission de « {store.name} » mise à jour : "
                f"{store.commission_label()}.",
            )
            return redirect("admin_dashboard:stores")

        messages.error(request, error)

    return render(
        request,
        "admin_dashboard/partials/_commission_form.html",
        {"store": store, "commission_types": Store.COMMISSION_TYPES},
    )


@login_required
@staff_required
def analytics(request):
    """The platform analytics plane.

    A single console that shows the whole platform: the headline
    numbers, the money per tenant, the COD funnel, the geography, the
    best sellers and the health of the scraping plane — with a link to
    the public front of every store.
    """
    payload = analytics_plane.analytics_payload()
    return render(
        request,
        "admin_dashboard/analytics.html",
        {
            "kpis": payload["kpis"],
            "store_rows": payload["stores"],
            "funnel": payload["funnel"],
            "revenue": payload["revenue"],
            # NOT ``governorates``: that name is already used by the
            # context processor for the list of the 24 governorates,
            # and the checkout modal unpacks it as pairs.
            "governorate_rows": payload["governorates"],
            "top_products": payload["top_products"],
            "scraper_rows": payload["scrapers"],
        },
    )


@login_required
@staff_required
def analytics_export(request):
    """Export the platform analytics as a CSV file."""
    import csv

    from django.http import HttpResponse

    payload = analytics_plane.analytics_payload()

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = (
        'attachment; filename="karthago-analytics.csv"'
    )
    writer = csv.writer(response)
    writer.writerow(
        [
            "Boutique",
            "Slug",
            "Statut",
            "Produits",
            "Produits en ligne",
            "Commandes",
            "CA (DT)",
            "Cout fournisseur (DT)",
            "Marge brute (DT)",
            "Commission (DT)",
            "Livraison net vendeur (DT)",
            "Livrees",
            "Commission realisee (DT)",
            "Taux realise (%)",
            "Commandes non reglees",
            "Commission non reglee (DT)",
            "Reglements",
            "Reglements payes",
        ]
    )
    for row in payload["stores"]:
        store = row["store"]
        writer.writerow(
            [
                store.name,
                store.slug,
                store.status_label,
                row["products"],
                row["published_products"],
                row["orders"],
                f"{row['gmv']:.3f}",
                f"{row['supplier_cost']:.3f}",
                f"{row['gross_margin']:.3f}",
                f"{row['platform_cut']:.3f}",
                f"{row['vendor_payout']:.3f}",
                row["delivered"],
                f"{row['delivered_cut']:.3f}",
                row["realized_rate"],
                row["unsettled_orders"],
                f"{row['unsettled_cut']:.3f}",
                row["settlements"],
                row["paid_settlements"],
            ]
        )
    return response


@login_required
@staff_required
def financials(request):
    """The financial ledger of the platform.

    Three KPI cards (realized commission, unsettled balance, average
    commission per delivered order), a per-store breakdown and the
    reconciliation action that builds a payout batch for a vendor.
    """
    from apps.orders.finance import platform_ledger, store_ledger

    since, until = _date_range(request)

    ledger = platform_ledger(since=since, until=until)
    selected_store_id = request.GET.get("store")
    selected_store = None
    if selected_store_id and selected_store_id.isdigit():
        selected_store = Store.objects.filter(pk=int(selected_store_id)).first()

    store_detail = store_ledger(selected_store, since=since, until=until) if selected_store else None

    return render(
        request,
        "admin_dashboard/financials.html",
        {
            "ledger": ledger,
            "by_store": ledger["by_store"],
            "stores": Store.objects.all(),
            "selected_store": selected_store,
            "store_detail": store_detail,
            "since": since,
            "until": until,
            "settlements": PayoutSettlement.objects.select_related("store").order_by(
                "-created_at"
            )[:30],
        },
    )


@login_required
@staff_required
def financials_export(request):
    """Export the ledger of a store (or of the platform) as a CSV file."""
    from apps.orders.finance import settlement_rows

    since, until = _date_range(request)
    store = None
    store_id = request.GET.get("store")
    if store_id and store_id.isdigit():
        store = Store.objects.filter(pk=int(store_id)).first()

    rows = settlement_rows(store, since=since, until=until)

    response = HttpResponse(content_type="text/csv; charset=utf-8")
    filename = f"ledger-{store.slug if store else 'platform'}.csv"
    response["Content-Disposition"] = f'attachment; filename="{filename}"'

    writer = csv.writer(response)
    writer.writerow(
        [
            "Commande",
            "Date",
            "Boutique",
            "Client",
            "CA brut",
            "Cout fournisseur",
            "Livraison",
            "Commission plateforme",
            "Net vendeur",
            "Reglee",
            "Lot",
        ]
    )
    for row in rows:
        writer.writerow(
            [
                row["order_id"],
                row["date"],
                row["store"],
                row["customer"],
                row["gross_total"],
                row["supplier_cost"],
                row["courier_cost"],
                row["platform_cut"],
                row["vendor_payout"],
                row["settled"],
                row["settlement"],
            ]
        )
    return response


@login_required
@staff_required
def settlement_create(request, store_id):
    """Build the payout batch of a store (reconciliation).

    Every delivered and paid order that is not settled yet is attached
    to a new batch. The batch keeps the totals of the commission and of
    the net payout.
    """
    from apps.orders.finance import build_settlement

    store = get_object_or_404(Store, pk=store_id)

    if request.method != "POST":
        return redirect("admin_dashboard:financials")

    payout_method = (
        request.POST.get("payout_method") or "Virement Bancaire / D17"
    ).strip()
    settlement = build_settlement(store, payout_method=payout_method)

    if settlement is None:
        messages.warning(
            request,
            f"Aucune commande livrée non réglée pour « {store.name} ».",
        )
    else:
        messages.success(
            request,
            f"Lot {settlement.reference} créé : {settlement.total_delivered_orders} "
            f"commandes, {settlement.net_payout_to_vendor} DT à verser.",
        )
    return redirect("admin_dashboard:financials")


@login_required
@staff_required
def settlement_paid(request, settlement_id):
    """Flag a payout batch as disbursed."""
    settlement = get_object_or_404(PayoutSettlement, pk=settlement_id)

    if request.method != "POST":
        return redirect("admin_dashboard:financials")

    settlement.mark_paid()
    messages.success(
        request,
        f"Lot {settlement.reference} marqué comme payé.",
    )
    return redirect("admin_dashboard:financials")


# ---------------------------------------------------------------------------
# Tenant management: create a vendor store, edit its commercial settings.
# ---------------------------------------------------------------------------
#: The fields the superadmin may change on a tenant.
STORE_FIELDS = [
    "name",
    "tagline",
    "description",
    "logo_url",
    "phone_number",
    "whatsapp_number",
    "address",
    "default_markup_percentage",
    "fixed_margin",
    "is_active",
]


def _parse_decimal(raw, default="0"):
    """Parse a decimal posted by the tenant form."""
    from decimal import InvalidOperation

    text = str(raw or "").strip().replace(",", ".")
    if not text:
        return Decimal(default)
    try:
        return Decimal(text)
    except (InvalidOperation, ValueError):
        raise ValueError(f"Valeur numérique invalide: {raw!r}")


def _unique_slug(name, exclude_pk=None):
    """Build a slug for a tenant, unique across the platform."""
    base = slugify(name)[:170] or "boutique"
    slug = base
    index = 2
    while (
        Store.objects.filter(slug=slug).exclude(pk=exclude_pk).exists()
    ):
        slug = f"{base}-{index}"
        index += 1
    return slug


@login_required
@staff_required
def store_create(request):
    """Create a new vendor tenant.

    The new store is online by default; the superadmin unchecks the box
    to keep it hidden from the storefront until its catalogue is filled.
    """
    if request.method == "POST":
        name = (request.POST.get("name") or "").strip()
        error = None

        if not name:
            error = "Le nom de la boutique est obligatoire."
        else:
            try:
                markup = _parse_decimal(
                    request.POST.get("default_markup_percentage"), "25"
                )
                margin = _parse_decimal(request.POST.get("fixed_margin"), "0")
                commission_rate = _parse_decimal(
                    request.POST.get("commission_rate"), "5"
                )
                flat_fee = _parse_decimal(
                    request.POST.get("flat_fee_per_order"), "0"
                )
            except ValueError as exc:
                error = str(exc)

        if error is None:
            owner = None
            owner_id = request.POST.get("owner") or ""
            if owner_id.isdigit():
                owner = get_object_or_404(
                    Store._meta.get_field("owner").related_model, pk=int(owner_id)
                )

            commission_type = (
                request.POST.get("commission_type")
                or Store.COMMISSION_TYPE_PERCENT
            ).strip()
            if commission_type not in dict(Store.COMMISSION_TYPES):
                commission_type = Store.COMMISSION_TYPE_PERCENT

            store = Store(
                name=name,
                slug=_unique_slug(request.POST.get("slug") or name),
                owner=owner,
                tagline=(request.POST.get("tagline") or "").strip(),
                description=(request.POST.get("description") or "").strip(),
                logo_url=(request.POST.get("logo_url") or "").strip(),
                phone_number=(request.POST.get("phone_number") or "").strip(),
                whatsapp_number=(request.POST.get("whatsapp_number") or "").strip(),
                address=(request.POST.get("address") or "").strip(),
                default_markup_percentage=markup,
                fixed_margin=margin,
                commission_type=commission_type,
                commission_rate=commission_rate,
                flat_fee_per_order=flat_fee,
                is_active=bool(request.POST.get("is_active")),
                # A tenant is never the platform flagship.
                is_platform_default=False,
            )
            store.save()
            messages.success(
                request,
                f"Boutique « {store.name} » créée. "
                f"Elle est en ligne sur {store.storefront_url}.",
            )
            return redirect("admin_dashboard:stores")

        messages.error(request, error)

    return render(
        request,
        "admin_dashboard/store_form.html",
        {
            "store": None,
            "is_create": True,
            "owners": _available_owners(),
            "commission_types": Store.COMMISSION_TYPES,
        },
    )


@login_required
@staff_required
def store_edit(request, store_id):
    """Edit the commercial settings of a tenant."""
    store = get_object_or_404(Store, pk=store_id)

    if request.method == "POST":
        name = (request.POST.get("name") or "").strip()
        error = None

        if not name:
            error = "Le nom de la boutique est obligatoire."
        else:
            try:
                markup = _parse_decimal(
                    request.POST.get("default_markup_percentage"),
                    str(store.default_markup_percentage),
                )
                margin = _parse_decimal(
                    request.POST.get("fixed_margin"), str(store.fixed_margin)
                )
                commission_rate = _parse_decimal(
                    request.POST.get("commission_rate"),
                    str(store.commission_rate),
                )
                flat_fee = _parse_decimal(
                    request.POST.get("flat_fee_per_order"),
                    str(store.flat_fee_per_order),
                )
            except ValueError as exc:
                error = str(exc)

        if error is None:
            owner = store.owner
            owner_id = request.POST.get("owner") or ""
            if owner_id == "":
                owner = None
            elif owner_id.isdigit():
                owner = get_object_or_404(
                    Store._meta.get_field("owner").related_model, pk=int(owner_id)
                )

            commission_type = (
                request.POST.get("commission_type") or store.commission_type
            ).strip()
            if commission_type not in dict(Store.COMMISSION_TYPES):
                commission_type = store.commission_type

            store.name = name
            store.owner = owner
            store.tagline = (request.POST.get("tagline") or "").strip()
            store.description = (request.POST.get("description") or "").strip()
            store.logo_url = (request.POST.get("logo_url") or "").strip()
            store.phone_number = (request.POST.get("phone_number") or "").strip()
            store.whatsapp_number = (request.POST.get("whatsapp_number") or "").strip()
            store.address = (request.POST.get("address") or "").strip()
            store.default_markup_percentage = markup
            store.fixed_margin = margin
            store.commission_type = commission_type
            store.commission_rate = commission_rate
            store.flat_fee_per_order = flat_fee
            store.is_active = bool(request.POST.get("is_active"))
            if store.is_platform_default:
                # The flagship owns the root of the site: taking it
                # offline would take the whole platform down.
                store.is_active = True
            store.save()
            messages.success(
                request, f"Boutique « {store.name} » mise à jour."
            )
            return redirect("admin_dashboard:stores")

        messages.error(request, error)

    return render(
        request,
        "admin_dashboard/store_form.html",
        {
            "store": store,
            "is_create": False,
            "owners": _available_owners(),
            "commission_types": Store.COMMISSION_TYPES,
        },
    )


def _available_owners():
    """The vendor accounts that can own a store.

    A user owns at most one store, so the accounts already owning a
    store are excluded from the list.
    """
    from django.contrib.auth import get_user_model

    user_model = get_user_model()
    taken = set(
        Store.objects.exclude(owner__isnull=True).values_list("owner_id", flat=True)
    )
    return user_model.objects.filter(is_staff=True).exclude(pk__in=taken)


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
