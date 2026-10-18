from django.urls import path
from . import views

app_name = "orders"

urlpatterns = [
    path("checkout/", views.CheckoutView.as_view(), name="checkout"),
    path("order/<int:order_id>/", views.OrderDetailView.as_view(), name="order_detail"),
]
