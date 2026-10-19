"""Catalog views for storefront."""
from django.shortcuts import render, get_object_or_404
from django.views.generic import ListView, DetailView
from django.db.models import Q, Count, F
from .models import Product, Category


# Sort options offered by the storefront toolbar.
SORT_OPTIONS = {
    "-created_at": "Nouveautés",
    "retail_price": "Prix : croissant",
    "-retail_price": "Prix : décroissant",
    "title": "Nom : A → Z",
    "discount": "Meilleures remises",
}

# Price buckets offered as one-tap filters in the sidebar.
PRICE_BUCKETS = [
    ("0", "50", "Moins de 50 DT"),
    ("50", "150", "50 – 150 DT"),
    ("150", "500", "150 – 500 DT"),
    ("500", "", "Plus de 500 DT"),
]


class CatalogFilterMixin:
    """Shared filtering logic for the storefront product listings.

    Every filter (category, search, price, stock, sort) is preserved when
    another one changes: the query string is rebuilt from the current
    request instead of being hard-coded per form.
    """

    def get_base_queryset(self):
        return Product.objects.filter(is_active=True).select_related("category", "supplier")

    def get_selected_category(self):
        """The category slug in play for this request.

        Comes either from the URL path (/category/<slug>/) or from the
        ?category= query string used by the HTMX sidebar.
        """
        slug = self.kwargs.get("category_slug") or self.request.GET.get("category", "")
        return (slug or "").strip()

    def get_queryset(self):
        queryset = self.get_base_queryset()

        category_slug = self.get_selected_category()
        if category_slug:
            queryset = queryset.filter(category__slug=category_slug)

        query = self.request.GET.get("q", "").strip()
        if query:
            queryset = queryset.filter(
                Q(title__icontains=query) | Q(description__icontains=query)
            )

        min_price = self.request.GET.get("min_price")
        if min_price:
            try:
                queryset = queryset.filter(retail_price__gte=float(min_price))
            except ValueError:
                pass
        max_price = self.request.GET.get("max_price")
        if max_price:
            try:
                queryset = queryset.filter(retail_price__lte=float(max_price))
            except ValueError:
                pass

        if self.request.GET.get("in_stock") == "1":
            queryset = queryset.filter(stock__gte=1)

        if self.request.GET.get("on_sale") == "1":
            # A product is "on sale" when the supplier shows a reference
            # price strictly above the price we actually charge.
            queryset = queryset.filter(
                compare_at_price__gt=0, raw_cost__lt=F("compare_at_price")
            )

        return self.apply_sort(queryset)

    def apply_sort(self, queryset):
        sort_by = self.request.GET.get("sort_by", "-created_at")
        if sort_by == "retail_price":
            return queryset.order_by("retail_price")
        if sort_by == "-retail_price":
            return queryset.order_by("-retail_price")
        if sort_by == "title":
            return queryset.order_by("title")
        if sort_by == "discount":
            # Biggest absolute discount first; products without a reference
            # price get a negative gain and therefore sort last.
            return queryset.annotate(
                _gain=F("compare_at_price") - F("raw_cost")
            ).order_by("-_gain")
        return queryset.order_by("-created_at")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        selected_category = self.get_selected_category()
        context["selected_category"] = selected_category
        context["min_price"] = self.request.GET.get("min_price", "")
        context["max_price"] = self.request.GET.get("max_price", "")
        context["in_stock"] = self.request.GET.get("in_stock", "")
        context["sort_by"] = self.request.GET.get("sort_by", "-created_at")
        context["q"] = self.request.GET.get("q", "")
        context["total_count"] = self.get_queryset().count()
        context["sort_options"] = SORT_OPTIONS
        context["price_buckets"] = PRICE_BUCKETS
        return context


class ProductListView(CatalogFilterMixin, ListView):
    model = Product
    template_name = "storefront/index.html"
    context_object_name = "products"
    paginate_by = 24

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["categories"] = Category.objects.annotate(
            n=Count("products", filter=Q(products__is_active=True))
        ).order_by("name")
        context["page_title"] = "Notre catalogue"
        context["page_subtitle"] = (
            "Découvrez nos produits avec livraison à travers toute la Tunisie."
        )
        return context


class HomeView(ListView):
    """Storefront landing page: hero, trust badges, categories, deals."""

    model = Product
    template_name = "storefront/home.html"
    context_object_name = "new_arrivals"
    paginate_by = 8

    def get_queryset(self):
        return (
            Product.objects.filter(is_active=True)
            .select_related("category", "supplier")
            .order_by("-created_at")
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        base = Product.objects.filter(is_active=True)

        categories = Category.objects.annotate(
            n=Count("products", filter=Q(products__is_active=True))
        ).order_by("-n", "name")
        populated = [c for c in categories if c.n > 0]

        # Flash deals: the biggest supplier reductions still in stock.
        flash_deals = list(
            base.filter(compare_at_price__gt=0, raw_cost__lt=F("compare_at_price"))
            .annotate(_gain=F("compare_at_price") - F("raw_cost"))
            .order_by("-_gain")[:8]
        )

        context["total_products"] = base.count()
        context["supplier_count"] = base.values("supplier_id").distinct().count()
        context["category_count"] = len(populated)
        context["showcase_categories"] = populated[:12]
        context["flash_deals"] = flash_deals
        context["hero_stats"] = [
            {"value": f"{base.count()}+", "label": "produits en catalogue"},
            {"value": f"{len(populated)}", "label": "catégories"},
            {"value": "24-48h", "label": "délai de livraison"},
            {"value": "100%", "label": "paiement à la livraison"},
        ]
        context["trust_badges"] = [
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
        ]
        return context


class CategoryListView(CatalogFilterMixin, ListView):
    """Landing page for a single category: /category/<slug>/."""

    model = Product
    template_name = "storefront/category.html"
    context_object_name = "products"
    paginate_by = 24

    def get_selected_category(self):
        slug = self.kwargs.get("category_slug", "")
        if not slug:
            return ""
        # Guard against a slug that does not exist: the view 404s later.
        return slug

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        slug = self.get_selected_category()
        category = get_object_or_404(Category, slug=slug)
        context["category"] = category
        context["categories"] = Category.objects.annotate(
            n=Count("products", filter=Q(products__is_active=True))
        ).order_by("name")
        context["page_title"] = category.name
        context["page_subtitle"] = category.description or (
            f"Tous les produits de la catégorie {category.name}."
        )
        return context


class ProductDetailView(DetailView):
    model = Product
    template_name = "storefront/product_detail.html"
    context_object_name = "product"
    slug_field = "id"
    slug_url_kwarg = "product_id"

    def get_queryset(self):
        # An inactive product (out of stock, removed by the supplier) must
        # not be reachable: its page would otherwise offer a dead "buy" CTA.
        return (
            Product.objects.filter(is_active=True)
            .select_related("category", "supplier")
        )


def product_search(request):
    """HTMX instant search endpoint returning product cards."""
    query = request.GET.get("q", "").strip()
    products = Product.objects.none()
    if query:
        products = (
            Product.objects.filter(is_active=True)
            .filter(Q(title__icontains=query) | Q(description__icontains=query))
            .select_related("category")[:8]
        )
    return render(
        request,
        "storefront/partials/_search_results.html",
        {"products": products, "query": query},
    )


def category_tree(request):
    """HTMX endpoint returning the category tree for the filter sidebar."""
    categories = Category.objects.annotate(
        n=Count("products", filter=Q(products__is_active=True))
    ).order_by("name")
    return render(
        request,
        "storefront/partials/_category_tree.html",
        {
            "categories": categories,
            "selected_category": request.GET.get("category", ""),
        },
    )
