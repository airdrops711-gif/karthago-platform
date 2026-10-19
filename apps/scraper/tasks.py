"""Celery tasks for periodic scraping and sync."""
import asyncio
import random
import time
from decimal import Decimal
from celery import shared_task
from django.utils import timezone
from .models import ScrapedSource, ScraperLog
from .engines import get_engine

# Suppliers rate-limit / bot-block when hit back-to-back. The scraper waits
# this long (plus jitter) between two different source domains.
DOMAIN_DELAY_SECONDS = 3.0
DOMAIN_DELAY_JITTER = 2.0


def _asyncio_run(coro):
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


def _domain_of(url):
    """Extract the registrable-ish host from a URL."""
    from urllib.parse import urlsplit

    try:
        host = (urlsplit(url).netloc or "").lower()
        return host[4:] if host.startswith("www.") else host
    except Exception:
        return ""


def polite_delay(url, last_domain, last_time):
    """Sleep before hitting a different domain. Returns (domain, timestamp)."""
    domain = _domain_of(url)
    now = time.time()
    if last_domain and domain and domain != last_domain:
        wait = DOMAIN_DELAY_SECONDS + random.uniform(0, DOMAIN_DELAY_JITTER)
        elapsed = now - last_time
        if elapsed < wait:
            time.sleep(wait - elapsed)
    return domain, time.time()


@shared_task(bind=True)
def sync_source(self, source_id):
    """Scrape a single source and persist products."""
    try:
        source = ScrapedSource.objects.get(pk=source_id)
    except ScrapedSource.DoesNotExist:
        return {"error": f"Source {source_id} not found"}

    log = ScraperLog.objects.create(source=source, status="running")

    selectors = {
        "product_container": source.product_container_selector,
        "title": source.title_selector,
        "price": source.price_selector,
        "price_fallbacks": getattr(source, "price_fallbacks", None) or [],
        "stock": source.stock_selector,
        "images": source.images_selector,
        "brand": getattr(source, "brand_selector", ""),
        "model": getattr(source, "model_selector", ""),
        "category": getattr(source, "category_selector", ""),
    }

    engine = get_engine(source.engine)
    results, error = _asyncio_run(engine.scrape(source, selectors))

    from apps.catalog.models import Product, Supplier, MarginRule, Category, ProductImage
    from django.utils.text import slugify

    supplier, _ = Supplier.objects.get_or_create(name=source.name)
    # Use the source-specific category when configured, else fall back to General
    cat_name = (source.category_name or "General").strip() or "General"
    category, _ = Category.objects.get_or_create(
        name=cat_name,
        defaults={"slug": slugify(cat_name)[:100] or "general"},
    )
    margin_rule, _ = MarginRule.objects.get_or_create(
        name="Default",
        defaults={"markup_percent": Decimal("30"), "fixed_margin_fee": Decimal("5.000")},
    )

    found = 0
    updated = 0
    errors = []
    skipped_no_price = 0
    for item in results:
        found += 1
        # Cap stock to a reasonable max to avoid integer overflow
        stock_val = min(item["stock"], 999999)
        # Use the product's own URL when available so each source row is unique
        item_url = item.get("url") or source.base_url
        if item_url.startswith("//"):
            item_url = "https:" + item_url
        # Guard against column length limits (e.g. very long AliExpress URLs).
        item_url = item_url[:500]
        title = (item.get("title") or "").strip()[:255]
        if not title:
            continue
        # Skip landing/category links that the container link heuristic picked up.
        if item.get("is_product") is False:
            continue
        # A product with no parseable price is not sellable; skip it instead of
        # storing a zero-cost item.
        if not item.get("price") or item["price"] <= 0:
            skipped_no_price += 1
            continue
        try:
            # Key on the normalised URL only. Two distinct products can share a
            # title, and the same product can appear in several category pages.
            obj, created = Product.objects.update_or_create(
                source=item_url,
                defaults={
                    "title": title,
                    "supplier": supplier,
                    "category": category,
                    "margin_rule": margin_rule,
                    "raw_cost": item["price"],
                    "currency": source.currency or "TND",
                    "currency_rate": source.currency_rate or Decimal("1"),
                    "markup_percent": margin_rule.markup_percent,
                    "fixed_margin_fee": margin_rule.fixed_margin_fee,
                    "stock": stock_val,
                    "description": title[:200],
                    "is_active": stock_val > 0,
                },
            )
        except Exception as exc:
            # One malformed product must not abort the whole source.
            errors.append(f"{title[:40]!r}: {type(exc).__name__}: {str(exc)[:120]}")
            continue
        # Save product images
        images_raw = item.get("images", "")
        if images_raw:
            # Clear existing images and re-add
            obj.images.all().delete()
            img_list = [img.strip() for img in images_raw.split(",") if img.strip()]
            for idx, img_url in enumerate(img_list[:5]):  # Limit to 5 images
                try:
                    ProductImage.objects.create(
                        product=obj,
                        image=img_url[:500],
                        alt_text=obj.title[:255],
                        is_primary=(idx == 0),
                        order=idx,
                    )
                except Exception as exc:
                    errors.append(f"image {img_url[:40]!r}: {type(exc).__name__}: {str(exc)[:100]}")
        if not created:
            updated += 1

    log.finished_at = timezone.now()
    log.products_found = found
    log.products_updated = updated
    detail = error or ""
    if errors:
        detail = (detail + " | " if detail else "") + "; ".join(errors[:5])
    log.errors = detail[:2000]
    if error:
        log.status = "completed_with_errors"
    elif errors:
        log.status = "completed_with_errors"
    else:
        log.status = "completed"
    log.save()

    return {
        "found": found,
        "updated": updated,
        "skipped_no_price": skipped_no_price,
        "errors": error or ("; ".join(errors[:3]) if errors else None),
    }


@shared_task(bind=True)
def sync_all_sources(self):
    """Scrape every enabled source, pausing between supplier domains.

    A single failing source must not abort the whole run.
    """
    results = []
    last_domain = ""
    last_time = 0.0
    for source in ScrapedSource.objects.all().order_by("name"):
        last_domain, last_time = polite_delay(
            source.base_url, last_domain, last_time
        )
        try:
            res = sync_source(source.id)
        except Exception as exc:
            res = {
                "found": 0,
                "updated": 0,
                "errors": f"{type(exc).__name__}: {str(exc)[:200]}",
            }
        results.append({"source": source.name, **res})
    total = sum(r.get("found", 0) for r in results)
    return {"total_found": total, "sources": results}
