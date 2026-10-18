"""Catalog views for storefront."""
from django.shortcuts import render, get_object_or_404
from django.views.generic import ListView, DetailView
from .models import Product


class ProductListView(ListView):
    model = Product
    template_name = "storefront/index.html"
    context_object_name = "products"
    paginate_by = 20

    def get_queryset(self):
        return Product.objects.filter(is_active=True, stock__gt=0)


class ProductDetailView(DetailView):
    model = Product
    template_name = "storefront/product_detail.html"
    context_object_name = "product"
    slug_field = "id"
    slug_url_kwarg = "product_id"

    def get_queryset(self):
        return Product.objects.filter(is_active=True)
