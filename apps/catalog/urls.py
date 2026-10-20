from django.urls import path

from . import flagship_views, substore_views

app_name = "catalog"

urlpatterns = [
    # ---- flagship: the root of the site --------------------------------
    path("", flagship_views.FlagshipHomeView.as_view(), name="home"),
    path("catalogue/", flagship_views.FlagshipCatalogView.as_view(), name="product_list"),
    path(
        "category/<slug:category_slug>/",
        flagship_views.FlagshipCategoryView.as_view(),
        name="category_detail",
    ),
    path(
        "product/<int:product_id>/",
        flagship_views.FlagshipProductView.as_view(),
        name="product_detail",
    ),
    path(
        "product/p/<int:product_id>/",
        flagship_views.CentralPoolProductView.as_view(),
        name="pool_product_detail",
    ),
    path("search/", flagship_views.product_search, name="search"),
    path("category-tree/", flagship_views.category_tree, name="category_tree"),

    # ---- vendor sub-stores: /s/<slug>/ ---------------------------------
    path("s/<slug:store_slug>/", substore_views.SubStoreHomeView.as_view(), name="substore_home"),
    path(
        "s/<slug:store_slug>/catalogue/",
        substore_views.SubStoreCatalogView.as_view(),
        name="substore_catalog",
    ),
    path(
        "s/<slug:store_slug>/product/<int:product_id>/",
        substore_views.SubStoreProductView.as_view(),
        name="substore_product",
    ),
]
