"""Create the platform flagship and move the existing catalogue into it.

The platform becomes multi-tenant at the row level, but the 4 000+ scraped
products already in the database belong to the flagship. This migration:

1. creates the flagship store (or reuses it),
2. creates one ``StoreProduct`` per active central product, linked to its
   source row so the origin stays traceable,
3. backfills the tenant of every legacy customer, order and cart.

Everything is idempotent: re-running it does not duplicate rows.
"""
from decimal import Decimal

from django.db import migrations
from django.utils.text import slugify


FLAGSHIP_NAME = "Karthago"
FLAGSHIP_SLUG = "karthago"


def _flagship(store_model):
    """Return the flagship store, creating it when missing."""
    flagship = store_model.objects.filter(is_platform_default=True).order_by("id").first()
    if flagship is not None:
        return flagship

    flagship = store_model.objects.filter(slug=FLAGSHIP_SLUG).first()
    if flagship is None:
        flagship = store_model.objects.create(
            name=FLAGSHIP_NAME,
            slug=FLAGSHIP_SLUG,
            is_platform_default=True,
            tagline="Le e-commerce tunisien, sans boutique.",
            description=(
                "Plateforme Karthago : produits réels importés des meilleurs "
                "fournisseurs tunisiens, paiement à la livraison partout en "
                "Tunisie."
            ),
            phone_number="+216",
            address="Tunis, Tunisie",
            default_markup_percentage=Decimal("10.00"),
            fixed_margin=Decimal("0.000"),
            is_active=True,
        )
    else:
        flagship.is_platform_default = True
        flagship.save(update_fields=["is_platform_default"])
    return flagship


def forwards(apps, schema_editor):
    Store = apps.get_model("catalog", "Store")
    StoreProduct = apps.get_model("catalog", "StoreProduct")
    Product = apps.get_model("catalog", "Product")
    Customer = apps.get_model("orders", "Customer")
    Order = apps.get_model("orders", "Order")
    Cart = apps.get_model("orders", "Cart")

    flagship = _flagship(Store)

    # --- 1. the existing catalogue becomes the flagship inventory --------
    existing = StoreProduct.objects.filter(store=flagship).count()
    if existing == 0:
        for product in Product.objects.filter(is_active=True).order_by("id").iterator():
            images = [img.image for img in product.images.all() if img.image]
            StoreProduct.objects.create(
                store=flagship,
                scraped_source_product=product,
                title=product.title[:300],
                description=product.description,
                category=product.category.name if product.category else "",
                source_cost=product.raw_cost,
                selling_price=product.retail_price,
                image_url=images[0] if images else "",
                image_urls=images,
                external_url=product.source,
                in_stock=product.stock > 0,
                is_published=True,
                is_store_native=False,
            )

    # --- 2. the legacy rows belong to the flagship ------------------------
    Customer.objects.filter(store__isnull=True).update(store=flagship)
    Order.objects.filter(store__isnull=True).update(store=flagship)
    Cart.objects.filter(store__isnull=True).update(store=flagship)


def backwards(apps, schema_editor):
    """The tenant columns are nullable, so the rollback is a clean reset."""
    StoreProduct = apps.get_model("catalog", "StoreProduct")
    Customer = apps.get_model("orders", "Customer")
    Order = apps.get_model("orders", "Order")
    Cart = apps.get_model("orders", "Cart")

    StoreProduct.objects.filter(store__is_platform_default=True).delete()
    Customer.objects.update(store=None)
    Order.objects.update(store=None)
    Cart.objects.update(store=None)


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0006_store_storeproduct"),
        ("orders", "0004_cart_store_customer_store_order_store"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
