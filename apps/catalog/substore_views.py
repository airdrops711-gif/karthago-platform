"""Vendor sub-store storefront: ``/s/<store_slug>/``.

Every query in this module is scoped to ``request.tenant_store``. A
product belonging to another store can never appear here, whatever the
URL says.
"""
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, render
from django.views import View

from apps.catalog.models import StoreProduct
from apps.catalog.tenancy import resolve_category, sub_store_listing, sub_store_rank
from apps.core.middleware import tenant_required

SORT_OPTIONS = {
    "-created_at": "Nouveautés",
    "selling_price": "Prix : croissant",
    "-selling_price": "Prix : décroissant",
    "title": "Nom : A → Z",
}

PRICE_BUCKETS = [
    ("0", "50", "Moins de 50 DT"),
    ("50", "150", "50 – 150 DT"),
    ("150", "500", "150 – 500 DT"),
    ("500", "", "Plus de 500 DT"),
]


class SubStoreHomeView(View):
    """Landing page of a vendor sub-store."""

    @tenant_required
    def get(self, request, store_slug=None):
        store = request.tenant_store
        products = sub_store_listing(store)

        categories = (
            StoreProduct.objects.filter(store=store, is_published=True)
            .exclude(category="")
            .values("category")
            .annotate(n=Count("id"))
            .order_by("-n", "category")
        )

        context = {
            "store": store,
            "products": products[:12],
            "total_products": products.count(),
            "categories": categories,
            "is_sub_store": True,
        }
        return render(request, "storefront/substore_home.html", context)


class SubStoreCatalogView(View):
    """The catalogue of a vendor sub-store, with the usual filters."""

    @tenant_required
    def get(self, request, store_slug=None, page=1):
        store = request.tenant_store
        products = sub_store_listing(store)

        category = (request.GET.get("category") or "").strip()
        if category:
            products = products.filter(
                category__iexact=resolve_category(store, category)
            )

        query = (request.GET.get("q") or "").strip()
        if query:
            products = products.filter(
                Q(title__icontains=query) | Q(description__icontains=query)
            )

        min_price = request.GET.get("min_price")
        if min_price:
            try:
                products = products.filter(selling_price__gte=float(min_price))
            except ValueError:
                pass

        max_price = request.GET.get("max_price")
        if max_price:
            try:
                products = products.filter(selling_price__lte=float(max_price))
            except ValueError:
                pass

        if request.GET.get("in_stock") == "1":
            products = products.filter(in_stock=True)

        sort_by = request.GET.get("sort_by", "-created_at")
        if sort_by == "selling_price":
            products = products.order_by("selling_price")
        elif sort_by == "-selling_price":
            products = products.order_by("-selling_price")
        elif sort_by == "title":
            products = products.order_by("title")
        else:
            products = products.order_by(sub_store_rank(), "-created_at")

        paginator = Paginator(products, 24)
        page_obj = paginator.get_page(page)

        categories = (
            StoreProduct.objects.filter(store=store, is_published=True)
            .exclude(category="")
            .values("category")
            .annotate(n=Count("id"))
            .order_by("-n", "category")
        )

        context = {
            "store": store,
            "products": page_obj,
            "page_obj": page_obj,
            "categories": categories,
            "selected_category": category,
            "q": query,
            "min_price": min_price or "",
            "max_price": max_price or "",
            "in_stock": request.GET.get("in_stock", ""),
            "sort_by": sort_by,
            "sort_options": SORT_OPTIONS,
            "price_buckets": PRICE_BUCKETS,
            "total_count": products.count(),
            "is_sub_store": True,
        }
        return render(request, "storefront/substore_catalog.html", context)


class SubStoreProductView(View):
    """Product page of a vendor sub-store."""

    @tenant_required
    def get(self, request, product_id, store_slug=None):
        store = request.tenant_store
        product = get_object_or_404(
            StoreProduct.objects.select_related("store", "scraped_source_product"),
            pk=product_id,
            store=store,
            is_published=True,
        )
        images = [
            url
            for url in ([product.image_url] + list(product.image_urls or []))
            if url
        ]
        context = {
            "store": store,
            "product": product,
            "product_images": images,
            "is_sub_store": True,
        }
        return render(request, "storefront/product_detail.html", context)
