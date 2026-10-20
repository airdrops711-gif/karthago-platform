"""Multi-tenant search on top of Meilisearch.

The platform indexes its whole catalogue in a single Meilisearch index.
Every document carries the tenant it belongs to (``store_id`` and
``store_slug``), so a search is always scoped:

* the flagship searches the whole index and orders the curated products
  first (``is_featured_on_main:desc`` then ``tier_rank:asc``);
* a vendor sub-store filters on its own ``store_id`` and never sees
  the flagship's curation.

The client is a thin raw-HTTP one: no extra dependency, and the calls
degrade gracefully — when Meilisearch is unreachable the storefront
falls back to the database search.
"""
from __future__ import annotations

import logging

import httpx

from django.conf import settings

logger = logging.getLogger(__name__)

#: The single index holding every tenant's catalogue.
INDEX_NAME = "karthago_products"

#: How long a Meilisearch call may take before the caller falls back.
DEFAULT_TIMEOUT = 2.0

#: The tenant tier used for the ranking: 1 = native, 2 = imported.
TIER_NATIVE = 1
TIER_IMPORTED = 2


def _host():
    return getattr(settings, "MEILISEARCH_HOST", "") or ""


def _api_key():
    return getattr(settings, "MEILISEARCH_API_KEY", "") or ""


def is_available():
    """True when a Meilisearch host is configured."""
    return bool(_host())


def _headers():
    headers = {"Content-Type": "application/json"}
    key = _api_key()
    if key:
        headers["Authorization"] = f"Bearer {key}"
    return headers


def _client():
    return httpx.Client(
        base_url=_host(),
        headers=_headers(),
        timeout=DEFAULT_TIMEOUT,
    )


def _request(method, path, json=None, params=None):
    """One HTTP call to Meilisearch. Returns the decoded body or None."""
    if not is_available():
        return None
    try:
        with _client() as client:
            response = client.request(method, path, json=json, params=params)
            response.raise_for_status()
            return response.json()
    except Exception as exc:  # network, timeout, HTTP error
        logger.warning("Meilisearch %s %s failed: %s", method, path, exc)
        return None


# ---------------------------------------------------------------------------
# Index configuration
# ---------------------------------------------------------------------------
def configure_index():
    """Apply the multi-tenant settings to the index.

    ``store_id`` is filterable (tenant isolation), ``is_featured_on_main``
    and ``tier_rank`` are sortable (the flagship ranking) and ``price``
    is sortable for the price filters.
    """
    payload = {
        "searchableAttributes": ["title", "description", "category", "store_slug"],
        "filterableAttributes": [
            "store_id",
            "store_slug",
            "is_featured_on_main",
            "tier_rank",
            "in_stock",
            "category",
        ],
        "sortableAttributes": ["price", "tier_rank", "is_featured_on_main"],
        "rankingRules": [
            "words",
            "typo",
            "proximity",
            "attribute",
            "sort",
            "exactness",
        ],
        "pagination": {"maxTotalHits": 5000},
    }
    return _request("PATCH", f"/indexes/{INDEX_NAME}/settings", json=payload)


def create_index():
    """Create the index if it does not exist yet."""
    body = _request("GET", f"/indexes/{INDEX_NAME}")
    if body is not None:
        return body
    return _request("POST", "/indexes", json={"uid": INDEX_NAME, "primaryKey": "id"})


# ---------------------------------------------------------------------------
# Indexing
# ---------------------------------------------------------------------------
def document_for(store_product):
    """The search document of one catalogue row."""
    return {
        "id": store_product.id,
        "title": store_product.title,
        "description": (store_product.description or "")[:1000],
        "category": store_product.category or "",
        "store_id": store_product.store_id,
        "store_slug": store_product.store.slug if store_product.store_id else "",
        "is_featured_on_main": bool(store_product.is_featured_on_main),
        "tier_rank": store_product.tier_rank,
        "price": float(store_product.selling_price or 0),
        "in_stock": bool(store_product.in_stock),
        "url": store_product.store.storefront_url
        if store_product.store_id
        else "/",
    }


def index_products(store_products, *, batch_size=500):
    """Push catalogue rows to Meilisearch. Returns the number of documents sent."""
    documents = [document_for(product) for product in store_products]
    if not documents:
        return 0

    sent = 0
    for start in range(0, len(documents), batch_size):
        chunk = documents[start : start + batch_size]
        body = _request("POST", f"/indexes/{INDEX_NAME}/documents", json=chunk)
        if body is None:
            return sent
        sent += len(chunk)
    return sent


def index_store(store):
    """Index the whole catalogue of one store."""
    from apps.catalog.models import StoreProduct

    queryset = StoreProduct.objects.filter(
        store=store, is_published=True
    ).select_related("store")
    return index_products(queryset)


def delete_product(store_product):
    """Remove one document from the index."""
    return _request(
        "DELETE", f"/indexes/{INDEX_NAME}/documents/{store_product.id}"
    )


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------
def search(
    query,
    *,
    store=None,
    limit=24,
    offset=0,
    category="",
    in_stock_only=False,
    min_price=None,
    max_price=None,
    sort_by=None,
):
    """Search the catalogue of one tenant.

    ``store=None`` means the flagship: the whole index is searched and
    the curated products come first. A store filters on its own
    ``store_id``, so the tenants never mix.

    Returns the list of documents, or ``None`` when Meilisearch is
    unavailable (the caller then falls back to the database).
    """
    if not is_available():
        return None

    filters = []
    if store is not None and not store.is_platform_default:
        filters.append(f"store_id = {store.id}")
    if category:
        filters.append(f'category = "{category}"')
    if in_stock_only:
        filters.append("in_stock = true")
    if min_price is not None:
        filters.append(f"price >= {float(min_price)}")
    if max_price is not None:
        filters.append(f"price <= {float(max_price)}")

    params = {
        "limit": limit,
        "offset": offset,
    }
    if filters:
        params["filter"] = " AND ".join(filters)

    if store is not None and not store.is_platform_default:
        # A sub-store never shows the flagship's curation: its own
        # native inventory comes first.
        params["sort"] = ["tier_rank:asc"]
    else:
        params["sort"] = ["is_featured_on_main:desc", "tier_rank:asc"]

    if sort_by == "selling_price":
        params["sort"] = ["price:asc"]
    elif sort_by == "-selling_price":
        params["sort"] = ["price:desc"]
    elif sort_by == "title":
        params["sort"] = ["title:asc"]

    body = _request("POST", f"/indexes/{INDEX_NAME}/search", json={"q": query, **params})
    if body is None:
        return None
    return body.get("hits", [])


def search_ids(
    query,
    *,
    store=None,
    limit=24,
    offset=0,
    category="",
    in_stock_only=False,
    min_price=None,
    max_price=None,
    sort_by=None,
):
    """The ordered ids of the search results (used to sort a DB queryset)."""
    hits = search(
        query,
        store=store,
        limit=limit,
        offset=offset,
        category=category,
        in_stock_only=in_stock_only,
        min_price=min_price,
        max_price=max_price,
        sort_by=sort_by,
    )
    if hits is None:
        return None
    return [hit.get("id") for hit in hits if hit.get("id") is not None]
