"""Scraper admin views."""
from django.shortcuts import render
from .models import ScrapedSource, ScraperLog


def scraper_dashboard(request):
    sources = ScrapedSource.objects.all()
    logs = ScraperLog.objects.order_by("-started_at")[:20]
    return render(request, "dashboard/scrapers.html", {"sources": sources, "logs": logs})
