"""Flagship storefront views, served from the tenant catalogue.

The flagship owns the root of the site (``/``). Its catalogue is made of
``StoreProduct`` rows, so the flagship can show the curated products of
the platform before the native inventory, and the imported ones last.

The routes are unchanged: ``/`` is the home page, ``/catalogue/`` the
listing, ``/category/<slug>/`` a category page and ``/product/<id>/`` a
product page. A product page may now be reached in two ways:

* ``/product/<id>/`` — a product of the flagship (tenant catalogue),
* ``/product/p/<id>/`` — a product of the central scraped pool, shown as
  a preview inside the platform.

The listing keeps every filter of the previous version (category, search,
price bucket, stock, sort) and preserves the other facets in the links.
"""
import json

from django.core.paginator import Paginator
from django.db.models import Count, F, Q
from django.shortcuts import get_object_or_404, render
from django.views import View
from django.views.generic.base import ContextMixin

from apps.catalog.models import Category, Product, StoreProduct
from apps.catalog.tenancy import (
    featured_showcase,
    flagship_listing,
    flagship_store,
    resolve_category,
    store_category_counts,
)
from apps.core.middleware import tenant_required


# Sort options offered by the storefront toolbar.
SORT_OPTIONS = {
    "-created_at": "Nouveautés",
    "selling_price": "Prix : croissant",
    "-selling_price": "Prix : décroissant",
    "title": "Nom : A → Z",
    "featured": "Sélection de la plateforme",
}

# Price buckets offered as one-tap filters in the sidebar.
PRICE_BUCKETS = [
    ("0", "50", "Moins de 50 DT"),
    ("50", "150", "50 – 150 DT"),
    ("150", "500", "150 – 500 DT"),
    ("500", "", "Plus de 500 DT"),
]


def _flagship_or_none():
    return flagship_store()


def _order_by_ids(queryset, ids):
    """Reorder a queryset to follow the given list of ids.

    The rows outside the list keep their place at the end, so the
    pagination never loses a product.
    """
    from django.db.models import Case, IntegerField, When

    if not ids:
        return queryset
    order = Case(
        *[When(pk=product_id, then=position) for position, product_id in enumerate(ids)],
        default=len(ids),
        output_field=IntegerField(),
    )
    return queryset.order_by(order)


def _store_category_tree(store):
    """The category tree of the flagship, built from its own products."""
    return store_category_counts(store)


def _base_queryset(store):
    """The published products of the flagship, in display priority order."""
    return flagship_listing(store)


class FlagshipCatalogMixin(ContextMixin):
    """Shared filtering logic for the flagship listings.

    Every filter (category, search, price, stock, sort) is preserved when
    another one changes: the query string is rebuilt from the current
    request instead of being hard-coded per form.
    """

    def get_store(self):
        return self.request.tenant_store or _flagship_or_none()

    def get_base_queryset(self):
        return _base_queryset(self.get_store())

    def get_selected_category(self):
        """The category slug in play for this request.

        Comes either from the URL path (/category/<slug>/) or from the
        ?category= query string used by the HTMX sidebar.
        """
        slug = self.kwargs.get("category_slug") or self.request.GET.get("category", "")
        return (slug or "").strip()

    def get_category_name(self):
        """The stored category name matching the selected slug.

        The tenant categories are free text ("TV & Audio") while the URLs
        carry a slug ("tv-audio"), so the name is resolved before the
        queryset is filtered on it.
        """
        slug = self.get_selected_category()
        if not slug:
            return ""
        return resolve_category(self.get_store(), slug)

    def get_queryset(self):
        queryset = self.get_base_queryset()

        category_name = self.get_category_name()
        if category_name:
            queryset = queryset.filter(category__iexact=category_name)

        query = self.request.GET.get("q", "").strip()
        if query:
            queryset = queryset.filter(
                Q(title__icontains=query) | Q(description__icontains=query)
            )

        min_price = self.request.GET.get("min_price")
        if min_price:
            try:
                queryset = queryset.filter(selling_price__gte=float(min_price))
            except ValueError:
                pass
        max_price = self.request.GET.get("max_price")
        if max_price:
            try:
                queryset = queryset.filter(selling_price__lte=float(max_price))
            except ValueError:
                pass

        if self.request.GET.get("in_stock") == "1":
            queryset = queryset.filter(in_stock=True)

        return self.apply_sort(queryset)

    def get_search_ids(self, queryset):
        """The Meilisearch ranking of the results, when the engine is up.

        Meilisearch returns the rows already ordered by relevance, so the
        database queryset is reordered to match. When the engine is
        unreachable, ``None`` is returned and the database order stands.
        """
        query = self.request.GET.get("q", "").strip()
        if not query:
            return None

        from apps.catalog import search as search_module

        min_price = self.request.GET.get("min_price")
        max_price = self.request.GET.get("max_price")
        try:
            min_price = float(min_price) if min_price else None
            max_price = float(max_price) if max_price else None
        except ValueError:
            min_price = max_price = None

        ids = search_module.search_ids(
            query,
            store=self.get_store(),
            limit=200,
            category=self.get_category_name(),
            in_stock_only=self.request.GET.get("in_stock") == "1",
            min_price=min_price,
            max_price=max_price,
        )
        if not ids:
            return None

        # Keep the tenant scope: only the ids that belong to the
        # queryset survive.
        allowed = set(queryset.values_list("id", flat=True))
        return [product_id for product_id in ids if product_id in allowed]

    def apply_sort(self, queryset):
        sort_by = self.request.GET.get("sort_by", "-created_at")
        if sort_by == "selling_price":
            return queryset.order_by("selling_price", "-created_at")
        if sort_by == "-selling_price":
            return queryset.order_by("-selling_price", "-created_at")
        if sort_by == "title":
            return queryset.order_by("title")
        if sort_by == "featured":
            return queryset.order_by(
                "display_rank", "-featured_priority", "-created_at"
            )
        return queryset.order_by("display_rank", "-created_at")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        selected_category = self.get_selected_category()
        store = self.get_store()
        context["selected_category"] = selected_category
        context["category_name"] = self.get_category_name() or selected_category
        context["min_price"] = self.request.GET.get("min_price", "")
        context["max_price"] = self.request.GET.get("max_price", "")
        context["in_stock"] = self.request.GET.get("in_stock", "")
        context["sort_by"] = self.request.GET.get("sort_by", "-created_at")
        context["q"] = self.request.GET.get("q", "")
        context["total_count"] = self.get_queryset().count()
        context["sort_options"] = SORT_OPTIONS
        context["price_buckets"] = PRICE_BUCKETS
        context["categories"] = _store_category_tree(store)
        context["store"] = store
        return context


class FlagshipHomeView(View):
    """Storefront landing page: hero, trust badges, showcase, new arrivals.

    The curated showcase comes first — it is the platform's own selection
    — then the newest products of the flagship catalogue.
    """

    def get(self, request):
        store = request.tenant_store or _flagship_or_none()
        showcase = featured_showcase(store, limit=8)
        listing = flagship_listing(store)

        categories = _store_category_tree(store)
        total_products = listing.count()

        # The newest products of the tenant catalogue, for the home page.
        new_arrivals = list(listing[:8])

        context = {
            "store": store,
            "total_products": total_products,
            "supplier_count": Product.objects.filter(is_active=True)
            .values("supplier_id")
            .distinct()
            .count(),
            "category_count": len(categories),
            "showcase_categories": categories[:12],
            "showcase": showcase,
            "flash_deals": list(
                listing.filter(in_stock=True).order_by("-created_at")[:8]
            ),
            "new_arrivals": new_arrivals,
            "hero_stats": [
                {"value": f"{total_products}+", "label": "produits en catalogue"},
                {"value": f"{len(categories)}", "label": "catégories"},
                {"value": "24-48h", "label": "délai de livraison"},
                {"value": "100%", "label": "paiement à la livraison"},
            ],
            "trust_badges": [
                {
                    "icon": "🚚",
                    "title": "Livraison 24-48h",
                    "text": "Dans toute la Tunisie",
                },
                {
                    "icon": "💵",
                    "title": "Paiement à la livraison",
                    "text": "Vous payez à la réception",
                },
                {
                    "icon": "↩️",
                    "title": "Retour sous 30 jours",
                    "text": "Satisfait ou remboursé",
                },
                {
                    "icon": "🏷️",
                    "title": "Prix-direct fournisseur",
                    "text": "Marge transparente de 10%",
                },
            ],
        }

        # ItemList of the newest products, for the home page.
        context["itemlist_schema"] = json.dumps(
            {
                "@context": "https://schema.org",
                "@type": "ItemList",
                "numberOfItems": len(new_arrivals),
                "itemListElement": [
                    {
                        "@type": "ListItem",
                        "position": index,
                        "url": request.build_absolute_uri(
                            f"/product/{product.id}/"
                        ),
                        "name": product.title[:120],
                    }
                    for index, product in enumerate(new_arrivals, start=1)
                ],
            },
            ensure_ascii=False,
        )
        return render(request, "storefront/home.html", context)


class FlagshipCatalogView(FlagshipCatalogMixin, View):
    """The flagship catalogue: /catalogue/."""

    def get(self, request, page=1):
        products = self.get_queryset()
        search_ids = self.get_search_ids(products)
        if search_ids:
            products = _order_by_ids(products, search_ids)
        paginator = Paginator(products, 24)
        page_obj = paginator.get_page(page)

        context = self.get_context_data()
        context.update(
            {
                "products": page_obj,
                "page_obj": page_obj,
                "paginator": paginator,
                "page_title": "Notre catalogue",
                "page_subtitle": (
                    "Découvrez nos produits avec livraison à travers toute la Tunisie."
                ),
            }
        )
        return render(request, "storefront/index.html", context)


class FlagshipCategoryView(FlagshipCatalogMixin, View):
    """Landing page for a single category: /category/<slug>/."""

    def get(self, request, category_slug, page=1):
        products = self.get_queryset()
        paginator = Paginator(products, 24)
        page_obj = paginator.get_page(page)

        # The category name comes from the tenant catalogue: the global
        # Category table stays the taxonomy of the central pool.
        name = (
            self.get_category_name()
            or products.values_list("category", flat=True).first()
            or category_slug.replace("-", " ").capitalize()
        )
        categories = _store_category_tree(self.get_store())
        current = next(
            (row for row in categories if row["category"].lower() == name.lower()),
            None,
        )

        context = self.get_context_data()
        context.update(
            {
                "products": page_obj,
                "page_obj": page_obj,
                "paginator": paginator,
                "category": current,
                "category_name": name,
                "page_title": name,
                "page_subtitle": f"Tous les produits de la catégorie {name}.",
            }
        )
        return render(request, "storefront/category.html", context)


class FlagshipProductView(View):
    """Product page of the flagship: /product/<id>/."""

    def get(self, request, product_id):
        store = request.tenant_store or _flagship_or_none()
        product = get_object_or_404(
            StoreProduct.objects.select_related("store", "scraped_source_product"),
            pk=product_id,
            store=store,
            is_published=True,
        )

        images = [url for url in ([product.image_url] + list(product.image_urls or [])) if url]
        base = request.build_absolute_uri("/")

        product_schema = {
            "@context": "https://schema.org",
            "@type": "Product",
            "name": product.title,
            "description": (product.description or product.title)[:500],
            "sku": str(product.id),
            "image": [request.build_absolute_uri(url) for url in images[:3]],
            "category": product.category or "Produit",
            "brand": {
                "@type": "Brand",
                "name": product.vendor_badge,
            },
            "offers": {
                "@type": "Offer",
                "url": request.build_absolute_uri(),
                "priceCurrency": "TND",
                "price": f"{product.selling_price:.3f}",
                "availability": (
                    "https://schema.org/InStock"
                    if product.in_stock
                    else "https://schema.org/OutOfStock"
                ),
                "itemCondition": "https://schema.org/NewCondition",
                "seller": {
                    "@type": "Organization",
                    "name": product.vendor_badge,
                },
            },
        }

        context = {
            "store": store,
            "product": product,
            "product_images": images,
            "product_schema": json.dumps(product_schema, ensure_ascii=False),
            "breadcrumb_schema": json.dumps(
                {
                    "@context": "https://schema.org",
                    "@type": "BreadcrumbList",
                    "itemListElement": [
                        {
                            "@type": "ListItem",
                            "position": 1,
                            "name": "Accueil",
                            "item": base,
                        },
                        {
                            "@type": "ListItem",
                            "position": 2,
                            "name": "Catalogue",
                            "item": request.build_absolute_uri("/catalogue/"),
                        },
                        {
                            "@type": "ListItem",
                            "position": 3,
                            "name": product.title[:120],
                            "item": request.build_absolute_uri(),
                        },
                    ],
                },
                ensure_ascii=False,
            ),
        }
        return render(request, "storefront/product_detail.html", context)


class CentralPoolProductView(View):
    """Preview of a central-pool product: /product/p/<id>/.

    The central pool is the raw material of the platform, not a
    storefront. Its pages are only reachable through the platform pages
    that reference it.
    """

    def get(self, request, product_id):
        product = get_object_or_404(
            Product.objects.filter(is_active=True).select_related(
                "category", "supplier"
            ),
            pk=product_id,
        )
        images = [img.url for img in product.images.all() if img.url]
        context = {
            "product": product,
            "product_images": images,
            "is_pool_preview": True,
        }
        return render(request, "storefront/pool_product.html", context)


def product_search(request):
    """HTMX instant search endpoint returning product cards."""
    store = request.tenant_store or _flagship_or_none()
    query = request.GET.get("q", "").strip()
    products = StoreProduct.objects.none()
    if query:
        products = (
            flagship_listing(store)
            .filter(Q(title__icontains=query) | Q(description__icontains=query))
            .select_related("store")[:8]
        )
    return render(
        request,
        "storefront/partials/_search_results.html",
        {"products": products, "query": query},
    )


def category_tree(request):
    """HTMX endpoint returning the category tree for the filter sidebar."""
    store = request.tenant_store or _flagship_or_none()
    return render(
        request,
        "storefront/partials/_category_tree.html",
        {
            "categories": _store_category_tree(store),
            "selected_category": request.GET.get("category", ""),
        },
    )


def global_categories(request):
    """The categories of the central pool, used by the admin dashboards."""
    return Category.objects.annotate(
        n=Count("products", filter=Q(products__is_active=True))
    ).order_by("name")
