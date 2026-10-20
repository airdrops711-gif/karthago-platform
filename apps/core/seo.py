"""SEO views: robots.txt, sitemap.xml and JSON-LD structured data."""
import json

from django.http import HttpResponse, JsonResponse
from django.urls import reverse
from django.utils.text import slugify
from django.views.decorators.cache import cache_control

from apps.catalog.models import Category, Product, Store, StoreProduct


def robots_txt(request):
    """robots.txt: allow the storefront, keep the admin and the
    operational pages out of the index."""
    lines = [
        "User-agent: *",
        "Allow: /",
        "Disallow: /admin/",
        "Disallow: /admin-dashboard/",
        "Disallow: /dashboard/",
        "Disallow: /scraper/",
        "Disallow: /orders/",
        "",
        f"Sitemap: {request.build_absolute_uri(reverse('seo:sitemap'))}",
        "",
    ]
    return HttpResponse("\n".join(lines), content_type="text/plain")


def _product_url(request, product):
    """Public URL of a tenant product, flagship or sub-store."""
    store = product.store
    if store.is_platform_default:
        return request.build_absolute_uri(
            reverse("catalog:product_detail", args=[product.id])
        )
    return request.build_absolute_uri(
        reverse("catalog:substore_product", args=[store.slug, product.id])
    )


@cache_control(max_age=3600, public=True)
def sitemap(request):
    """XML sitemap of the storefront pages.

    The catalogue is the tenant one: the flagship at the root and every
    vendor sub-store under ``/s/<slug>/``.
    """
    base = request.build_absolute_uri("/")
    urls = [
        (base, "daily", "1.0"),
        (request.build_absolute_uri(reverse("catalog:product_list")), "daily", "0.9"),
    ]

    flagship = (
        Store.objects.filter(is_platform_default=True).order_by("id").first()
    )

    # Category pages of the flagship, built from the tenant taxonomy.
    if flagship is not None:
        names = (
            StoreProduct.objects.filter(store=flagship, is_published=True)
            .exclude(category="")
            .values_list("category", flat=True)
            .distinct()
        )
        for name in names:
            slug = slugify(str(name))
            if not slug:
                continue
            urls.append(
                (
                    request.build_absolute_uri(
                        reverse("catalog:category_detail", args=[slug])
                    ),
                    "weekly",
                    "0.7",
                )
            )

    # Product pages: the catalogue is large, so only the most recent
    # products are listed to keep the sitemap under the 50 000 URL limit
    # and to prioritise the fresh content.
    for product in (
        StoreProduct.objects.filter(is_published=True)
        .select_related("store")
        .order_by("-created_at")[:5000]
    ):
        urls.append((_product_url(request, product), "weekly", "0.6"))

    # Vendor sub-stores: their home, their catalogue and their products.
    for store in Store.objects.filter(is_active=True, is_platform_default=False):
        urls.append(
            (
                request.build_absolute_uri(
                    reverse("catalog:substore_home", args=[store.slug])
                ),
                "weekly",
                "0.8",
            )
        )
        urls.append(
            (
                request.build_absolute_uri(
                    reverse("catalog:substore_catalog", args=[store.slug])
                ),
                "weekly",
                "0.7",
            )
        )
        for product in (
            StoreProduct.objects.filter(store=store, is_published=True)
            .order_by("-created_at")[:1000]
        ):
            urls.append((_product_url(request, product), "weekly", "0.6"))

    body = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ]
    for loc, changefreq, priority in urls:
        body.append("  <url>")
        body.append(f"    <loc>{loc}</loc>")
        body.append(f"    <changefreq>{changefreq}</changefreq>")
        body.append(f"    <priority>{priority}</priority>")
        body.append("  </url>")
    body.append("</urlset>")

    return HttpResponse(
        "\n".join(body), content_type="application/xml; charset=utf-8"
    )


def organization_ld(request):
    """Organization + WebSite structured data for the home page."""
    base = request.build_absolute_uri("/")
    data = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "Organization",
                "@id": f"{base}#organization",
                "name": "Karthago",
                "url": base,
                "logo": {
                    "@type": "ImageObject",
                    "url": request.build_absolute_uri("/static/img/favicon.svg"),
                },
                "description": (
                    "Importateur de produits depuis les fournisseurs tunisiens. "
                    "Paiement à la livraison dans toute la Tunisie."
                ),
                "areaServed": {"@type": "Country", "name": "Tunisie"},
                "contactPoint": {
                    "@type": "ContactPoint",
                    "telephone": "+216",
                    "contactType": "customer service",
                    "areaServed": "TN",
                    "availableLanguage": ["fr", "ar"],
                },
            },
            {
                "@type": "WebSite",
                "@id": f"{base}#website",
                "url": base,
                "name": "Karthago",
                "inLanguage": "fr-TN",
                "publisher": {"@id": f"{base}#organization"},
                "potentialAction": {
                    "@type": "SearchAction",
                    "target": {
                        "@type": "EntryPoint",
                        "urlTemplate": f"{base}search/?q={{search_term_string}}",
                    },
                    "query-input": "required name=search_term_string",
                },
            },
        ],
    }
    return JsonResponse(data, safe=False)


def breadcrumb_ld(request, items):
    """BreadcrumbList structured data from a list of (name, url) pairs."""
    base = request.build_absolute_uri("/")
    entries = []
    for index, (name, url) in enumerate(items, start=1):
        entries.append(
            {
                "@type": "ListItem",
                "position": index,
                "name": name,
                "item": request.build_absolute_uri(url),
            }
        )
    return {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": entries,
    }
