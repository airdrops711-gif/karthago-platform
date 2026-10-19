"""Scraper admin views."""
from django.shortcuts import render, get_object_or_404
from django.http import HttpResponse
from django.views import View
from .models import ScrapedSource, ScraperLog
from apps.scraper.tasks import sync_source


class ScraperDashboard(View):
    """Visual control plane for scraper sources."""

    def get(self, request):
        sources = ScrapedSource.objects.all()
        logs = ScraperLog.objects.order_by("-started_at")[:20]
        return render(request, "dashboard/scrapers.html", {"sources": sources, "logs": logs})


class RunScraperView(View):
    """Trigger a manual scrape for a single source via HTMX."""

    def post(self, request, source_id):
        source = get_object_or_404(ScrapedSource, pk=source_id)
        # Kick off async task
        sync_source.delay(source.id)
        return HttpResponse(
            '<span class="text-xs text-green-600 font-medium">T&e2;che lanc&e9;e (asynchrone)</span>'
        )
