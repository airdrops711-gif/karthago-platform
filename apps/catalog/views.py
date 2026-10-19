"""Catalog views for storefront."""
from django.shortcuts import render, get_object_or_404
from django.views.generic import ListView, DetailView
from django.db.models import Q
from .models import Product, Category


class ProductListView(ListView):
    model = Product
    template_name = "storefront/index.html"
    context_object_name = "products"
    paginate_by = 20

    def get_queryset(self):
        queryset = Product.objects.all().select_related("category")
        category_slug = self.request.GET.get("category")
        if category_slug:
            queryset = queryset.filter(category__slug=category_slug)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["categories"] = Category.objects.all()
        context["selected_category"] = self.request.GET.get("category", "")
        context["min_price"] = self.request.GET.get("min_price", "")
        context["max_price"] = self.request.GET.get("max_price", "")
        context["in_stock"] = self.request.GET.get("in_stock", "")
        context["sort_by"] = self.request.GET.get("sort_by", "-created_at")
        return context

    def get_queryset(self):
        queryset = Product.objects.all().select_related("category")
        category_slug = self.request.GET.get("category")
        if category_slug:
            queryset = queryset.filter(category__slug=category_slug)
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
        in_stock = self.request.GET.get("in_stock")
        if in_stock == "1":
            queryset = queryset.filter(stock__gte=1)
        sort_by = self.request.GET.get("sort_by", "-created_at")
        if sort_by == "retail_price":
            queryset = queryset.order_by("retail_price")
        elif sort_by == "-retail_price":
            queryset = queryset.order_by("-retail_price")
        elif sort_by == "title":
            queryset = queryset.order_by("title")
        else:
            queryset = queryset.order_by("-created_at")
        return queryset


class ProductDetailView(DetailView):
    model = Product
    template_name = "storefront/product_detail.html"
    context_object_name = "product"
    slug_field = "id"
    slug_url_kwarg = "product_id"

    def get_queryset(self):
        return Product.objects.all().select_related("category")


def product_search(request):
    """HTMX instant search endpoint returning product cards."""
    query = request.GET.get("q", "").strip()
    products = Product.objects.none()
    if query:
        products = Product.objects.filter(
            Q(title__icontains=query) | Q(description__icontains=query)
        ).select_related("category")[:8]
    return render(request, "storefront/partials/_search_results.html", {"products": products, "query": query})


def category_tree(request):
    """HTMX endpoint returning the category tree for the filter sidebar."""
    categories = Category.objects.all()
    return render(request, "storefront/partials/_category_tree.html", {"categories": categories})
