from django.urls import path
from . import views
from apps.catalog import product_ingestion

app_name = "dashboard"

urlpatterns = [
    path("", views.overview, name="overview"),
    path("finances/", views.finances, name="finances"),
    path("scrapers/", views.scrapers, name="scrapers"),
    path("orders/", views.orders_list, name="orders"),
    path("orders/<int:order_id>/", views.order_detail, name="order_detail"),
    path("orders/<int:order_id>/status/", views.order_update_status, name="order_update_status"),
    path("orders/<int:order_id>/note/", views.order_note, name="order_note"),
    path("orders/<int:order_id>/call/", views.order_call, name="order_call"),

    # Vendor product management (tenant-scoped).
    path("products/", product_ingestion.ProductCreateView.as_view(), name="product_create"),
    path("products/bulk/", product_ingestion.BulkImportView.as_view(), name="product_bulk"),
    path("products/import/", product_ingestion.ImportFromPoolView.as_view(), name="product_import"),
    path("products/<int:product_id>/toggle/", product_ingestion.ProductUpdateView.as_view(), name="product_toggle"),
    path("products/<int:product_id>/delete/", product_ingestion.ProductDeleteView.as_view(), name="product_delete"),
]
