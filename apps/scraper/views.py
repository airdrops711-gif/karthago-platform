"""Scraper admin views.

The control plane is a staff-only area: it exposes the supplier
registry and triggers scrapes, so it must not be reachable by an
anonymous visitor. The decorators are applied to the class with
``method_decorator``: applied to a method, the ``login_required``
wrapper would receive the view instance instead of the request.
"""
from django.contrib.auth.decorators import login_required, user_passes_test
from django.shortcuts import render, get_object_or_404
from django.http import HttpResponse
from django.utils.decorators import method_decorator
from django.views import View
from .models import ScrapedSource, ScraperLog
from apps.scraper.tasks import sync_source


def _is_staff(user):
    return user.is_active and user.is_staff


staff_required = user_passes_test(_is_staff)

staff_only = method_decorator([login_required, staff_required], name="dispatch")


@staff_only
class ScraperDashboard(View):
    """Visual control plane for scraper sources."""

    def get(self, request):
        sources = ScrapedSource.objects.all()
        logs = ScraperLog.objects.order_by("-started_at")[:20]
        return render(request, "dashboard/scrapers.html", {"sources": sources, "logs": logs})


@staff_only
class RunScraperView(View):
    """Trigger a manual scrape for a single source via HTMX."""

    def post(self, request, source_id):
        source = get_object_or_404(ScrapedSource, pk=source_id)
        # Kick off async task
        sync_source.delay(source.id)
        return HttpResponse(
            '<span class="text-xs text-green-600 font-medium">T&e2;che lanc&e9;e (asynchrone)</span>'
        )
