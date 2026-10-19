from django.urls import path
from . import views

app_name = "scraper"

urlpatterns = [
    path("", views.ScraperDashboard.as_view(), name="scraper_dashboard"),
    path("run/<int:source_id>/", views.RunScraperView.as_view(), name="run"),
]
