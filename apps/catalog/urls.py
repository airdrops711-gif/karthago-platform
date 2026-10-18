from django.urls import path
from . import views

app_name = "catalog"

urlpatterns = [
    path("", views.ProductListView.as_view(), name="product_list"),
    path("product/<int:product_id>/", views.ProductDetailView.as_view(), name="product_detail"),
]
