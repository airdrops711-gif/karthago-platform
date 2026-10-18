from django.urls import path
from . import views

app_name = "dashboard"

urlpatterns = [
    path("", views.overview, name="overview"),
    path("scrapers/", views.scrapers, name="scrapers"),
    path("orders/", views.orders_list, name="orders"),
]
