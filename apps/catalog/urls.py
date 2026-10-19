from django.urls import path
from . import views

app_name = "catalog"

urlpatterns = [
    path("", views.HomeView.as_view(), name="home"),
    path("catalogue/", views.ProductListView.as_view(), name="product_list"),
    path("category/<slug:category_slug>/", views.CategoryListView.as_view(), name="category_detail"),
    path("product/<int:product_id>/", views.ProductDetailView.as_view(), name="product_detail"),
    path("search/", views.product_search, name="search"),
    path("category-tree/", views.category_tree, name="category_tree"),
]
