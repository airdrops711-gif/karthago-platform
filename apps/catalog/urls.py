from django.urls import path
from . import views

app_name = "catalog"

urlpatterns = [
    path("", views.ProductListView.as_view(), name="product_list"),
    path("product/<int:product_id>/", views.ProductDetailView.as_view(), name="product_detail"),
    path("search/", views.product_search, name="search"),
    path("category-tree/", views.category_tree, name="category_tree"),
]
