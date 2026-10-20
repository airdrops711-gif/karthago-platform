"""URL configuration for Karthago Platform."""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from apps.core import views as core_views

urlpatterns = [
    path("admin/", admin.site.urls),
    path("healthz/", core_views.healthz, name="healthz"),
    path("", include("apps.core.seo_urls")),
    path("", include("apps.catalog.urls")),
    path("orders/", include("apps.orders.urls")),
    path("dashboard/", include("apps.dashboard.urls")),
    path("admin-dashboard/", include("apps.dashboard.admin_urls")),
    path("scraper/", include("apps.scraper.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
