from django.urls import path
from . import views

app_name = "dashboard"

urlpatterns = [
    path("", views.overview, name="overview"),
    path("scrapers/", views.scrapers, name="scrapers"),
    path("orders/", views.orders_list, name="orders"),
    path("orders/<int:order_id>/", views.order_detail, name="order_detail"),
    path("orders/<int:order_id>/status/", views.order_update_status, name="order_update_status"),
    path("orders/<int:order_id>/note/", views.order_note, name="order_note"),
    path("orders/<int:order_id>/call/", views.order_call, name="order_call"),
]
