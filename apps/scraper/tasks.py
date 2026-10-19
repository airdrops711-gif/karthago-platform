"""Celery tasks for periodic scraping and sync."""
import asyncio
from celery import shared_task
from django.utils import timezone
from .models import ScrapedSource, ScraperLog
from .engines import get_engine


def _asyncio_run(coro):
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


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
        "stock": source.stock_selector,
        "images": source.images_selector,
        "brand": getattr(source, "brand_selector", ""),
        "model": getattr(source, "model_selector", ""),
        "category": getattr(source, "category_selector", ""),
    }

    engine = get_engine(source.engine)
    results, error = _asyncio_run(engine.scrape(source, selectors))

    from apps.catalog.models import Product, Supplier, MarginRule, Category, ProductImage

    supplier, _ = Supplier.objects.get_or_create(name=source.name)
    category, _ = Category.objects.get_or_create(name="General", defaults={"slug": "general"})
    margin_rule, _ = MarginRule.objects.get_or_create(
        name="Default", defaults={"markup_percent": 30, "fixed_margin_fee": 5.000}
    )

    found = 0
    updated = 0
    for item in results:
        found += 1
        # Cap stock to a reasonable max to avoid integer overflow
        stock_val = min(item["stock"], 999999)
        obj, created = Product.objects.update_or_create(
            source=source.base_url,
            title=item["title"],
            defaults={
                "supplier": supplier,
                "category": category,
                "margin_rule": margin_rule,
                "raw_cost": item["price"],
                "markup_percent": margin_rule.markup_percent,
                "fixed_margin_fee": margin_rule.fixed_margin_fee,
                "stock": stock_val,
                "description": item.get("title", "")[:200],
                "is_active": stock_val > 0,
            },
        )
        # Save product images
        images_raw = item.get("images", "")
        if images_raw:
            # Clear existing images and re-add
            obj.images.all().delete()
            img_list = [img.strip() for img in images_raw.split(",") if img.strip()]
            for idx, img_url in enumerate(img_list[:5]):  # Limit to 5 images
                ProductImage.objects.create(
                    product=obj,
                    image=img_url,
                    alt_text=obj.title,
                    is_primary=(idx == 0),
                    order=idx,
                )
        if not created:
            updated += 1

    log.finished_at = timezone.now()
    log.products_found = found
    log.products_updated = updated
    log.errors = error or ""
    log.status = "completed" if not error else "completed_with_errors"
    log.save()

    return {"found": found, "updated": updated, "errors": error}
