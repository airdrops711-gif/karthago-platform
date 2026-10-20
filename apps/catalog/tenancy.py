"""Tenant-scoped catalogue queries.

Every storefront listing goes through this module. It is the single
place that knows the display ranking:

1. Curated products featured on the flagship come first.
2. Then the store's own native inventory.
3. Then the products imported from the central scraped pool.

The ranking is a database-level sort on the persisted ``display_rank``
column, so the pagination stays correct on large catalogues.
"""
from django.db.models import Case, IntegerField, Q, Value, When

from .models import Product, Store, StoreProduct

# The three display tiers.
RANK_CURATED = 0
RANK_NATIVE = 1
RANK_IMPORTED = 2

# A sub-store demotes the products curated on the main platform: the
# curation is a platform-level selection, it is not a sub-store priority.
SUB_STORE_RANK_NATIVE = 1
SUB_STORE_RANK_IMPORTED = 2
SUB_STORE_RANK_CURATED = 3


def flagship_store():
    """The platform flagship store (the owner of the root of the site)."""
    return (
        Store.objects.filter(is_platform_default=True)
        .order_by("id")
        .first()
    )


def store_products(store, *, published_only=True, in_stock_only=False):
    """Products of one store, in display priority order.

    The ranking is a database-level sort, not a Python sort, so the
    pagination stays correct on large catalogues.
    """
    if store is None:
        return StoreProduct.objects.none()

    queryset = StoreProduct.objects.filter(store=store)
    if published_only:
        queryset = queryset.filter(is_published=True)
    if in_stock_only:
        queryset = queryset.filter(in_stock=True)
    return _ranked(queryset, featured_first=False)


def _ranked(store_products_qs, featured_first=False):
    """Apply the priority ranking to a StoreProduct queryset.

    ``featured_first`` puts the rows curated on the flagship first. The
    flagship homepage needs it; a sub-store listing does not, because a
    sub-store never shows the flagship's curation.
    """
    if featured_first:
        return store_products_qs.order_by(
            "display_rank", "-featured_priority", "-created_at"
        )

    return store_products_qs.order_by("display_rank", "-created_at")


def sub_store_rank():
    """The ordering key of a sub-store listing.

    Native inventory first, then the products imported from the central
    pool, and finally the rows curated on the main platform: the curation
    belongs to the flagship and must never push a vendor's own products
    down in its own shop.
    """
    return Case(
        When(is_featured_on_main=True, then=Value(SUB_STORE_RANK_CURATED)),
        When(is_store_native=True, then=Value(SUB_STORE_RANK_NATIVE)),
        default=Value(SUB_STORE_RANK_IMPORTED),
        output_field=IntegerField(),
    )


def sub_store_listing(store, *, published_only=True):
    """Products of a sub-store: native inventory first, imports second."""
    queryset = StoreProduct.objects.filter(store=store)
    if published_only:
        queryset = queryset.filter(is_published=True)
    return queryset.order_by(sub_store_rank(), "-created_at")


def flagship_listing(store=None, *, published_only=True):
    """Products of the flagship, curated rows first."""
    store = store or flagship_store()
    if store is None:
        return StoreProduct.objects.none()
    queryset = StoreProduct.objects.filter(store=store)
    if published_only:
        queryset = queryset.filter(is_published=True)
    return _ranked(queryset, featured_first=True)


def featured_showcase(store=None, *, limit=12, in_stock_only=True):
    """The curated showcase of the flagship homepage.

    Only the products the superadmin explicitly flagged are shown, in
    the order given by ``featured_priority``.
    """
    if store is None:
        store = flagship_store()
    if store is None:
        return StoreProduct.objects.none()

    queryset = StoreProduct.objects.filter(
        is_featured_on_main=True, is_published=True
    )
    if in_stock_only:
        queryset = queryset.filter(in_stock=True)
    return queryset.select_related("store", "scraped_source_product").order_by(
        "-featured_priority", "-featured_curated_at"
    )[:limit]


def central_pool(*, limit=None, search=""):
    """The central scraped pool, browsable by the vendors.

    The pool is global: it is the raw material every store imports from.
    """
    queryset = Product.objects.filter(is_active=True).select_related(
        "category", "supplier"
    )
    if search:
        queryset = queryset.filter(
            Q(title__icontains=search) | Q(description__icontains=search)
        )
    queryset = queryset.order_by("-created_at")
    if limit:
        queryset = queryset[:limit]
    return queryset


def resolve_category(store, slug):
    """Resolve a URL slug back to the category name used by a store.

    The tenant categories are free text ("TV & Audio"), but the URLs are
    clean slugs ("tv-audio"). The catalogue filters on the stored name, so
    the slug has to be mapped back to it before filtering.
    """
    if not slug:
        return ""

    from django.utils.text import slugify

    wanted = slugify(str(slug))
    for row in store_category_counts(store):
        if slugify(row["category"]) == wanted:
            return row["category"]
    return str(slug)


def store_category_counts(store, *, published_only=True):
    """The free-text categories actually used by a store.

    Each store keeps its own category names, so the sidebar is built from
    the products of that store and not from the global taxonomy.
    """
    from django.db.models import Count

    if store is None:
        return []
    queryset = StoreProduct.objects.filter(store=store)
    if published_only:
        queryset = queryset.filter(is_published=True)
    return (
        queryset.exclude(category="")
        .values("category")
        .annotate(n=Count("id"))
        .order_by("-n", "category")
    )


def sync_flagship_product(product):
    """Create or refresh the flagship entry of a central-pool product.

    The central pool is the raw material; the flagship catalogue is what
    the platform actually sells. Every scraped product therefore gets one
    ``StoreProduct`` row in the flagship, kept in sync with the source
    row (price, stock, images, title).

    The function is idempotent: the flagship row is matched on its link
    to the source product, so a re-scrape updates it instead of
    duplicating it.
    """
    from django.utils.text import slugify

    store = flagship_store()
    if store is None or product is None:
        return None

    images = [img.image for img in product.images.all() if img.image]
    title = product.title[:300]

    entry = (
        StoreProduct.objects.filter(
            store=store, scraped_source_product=product
        )
        .order_by("id")
        .first()
    )
    if entry is None:
        entry = StoreProduct(store=store, scraped_source_product=product)

    entry.title = title
    entry.description = product.description or title
    entry.category = product.category.name if product.category else ""
    entry.source_cost = product.raw_cost
    entry.selling_price = product.retail_price
    entry.image_url = images[0] if images else ""
    entry.image_urls = images
    entry.external_url = product.source
    entry.in_stock = product.stock > 0
    entry.is_published = True
    entry.is_store_native = False

    if not entry.slug:
        entry.slug = slugify(title)[:340] or "produit"

    # Keep the slug unique inside the flagship catalogue.
    base = entry.slug
    index = 2
    while (
        StoreProduct.objects.filter(store=store, slug=entry.slug)
        .exclude(pk=entry.pk)
        .exists()
    ):
        entry.slug = f"{base}-{index}"
        index += 1

    entry.save()
    return entry
