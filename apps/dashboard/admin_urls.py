"""Platform superadmin routes: ``/admin-dashboard/``.

These views see the whole platform: every store, every order, the
curation of the flagship and the scraper registry. They are restricted
to staff accounts.
"""
from django.urls import path

from . import admin_views

app_name = "admin_dashboard"

urlpatterns = [
    path("", admin_views.overview, name="overview"),
    path("stores/", admin_views.stores, name="stores"),
    path("stores/new/", admin_views.store_create, name="store_create"),
    path("stores/<int:store_id>/edit/", admin_views.store_edit, name="store_edit"),
    path("curation/", admin_views.curation, name="curation"),
    path(
        "curation/<int:product_id>/toggle/",
        admin_views.curation_toggle,
        name="curation_toggle",
    ),
    path(
        "curation/<int:product_id>/priority/",
        admin_views.curation_priority,
        name="curation_priority",
    ),
    path("orders/", admin_views.orders, name="orders"),
    path("scrapers/", admin_views.scrapers, name="scrapers"),
    path("scrapers/sandbox/", admin_views.selector_sandbox, name="selector_sandbox"),
    path(
        "scrapers/<int:source_id>/run/",
        admin_views.scraper_run,
        name="scraper_run",
    ),
    path(
        "scrapers/<int:source_id>/status/",
        admin_views.scraper_status,
        name="scraper_status",
    ),
    path("central-pool/", admin_views.central_pool_view, name="central_pool"),
]
