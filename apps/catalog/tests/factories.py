"""Shared test fixtures for the multi-tenant catalogue.

The platform has three layers and the tests must not mix them:

* ``Product`` — the central scraped pool (owned by the Celery scraper),
* ``StoreProduct`` — the tenant catalogue (what a storefront displays),
* ``Store`` — the tenant itself.

Every test that touches the storefront needs a store with products, so the
helpers here build that arrangement once.
"""
from decimal import Decimal

from apps.catalog.models import (
    Category,
    MarginRule,
    Product,
    Store,
    StoreProduct,
    Supplier,
)


def make_flagship(name="Karthago", slug="karthago", markup="10.00"):
    """Return the platform flagship store, creating it when missing.

    The data migration ``0007_flagship_bootstrap`` already creates the
    flagship in the test database, so the helper reuses it instead of
    failing on the unique slug.
    """
    flagship = Store.objects.filter(is_platform_default=True).order_by("id").first()
    if flagship is None:
        flagship = Store.objects.filter(slug=slug).first()
    if flagship is None:
        flagship = Store.objects.create(
            name=name,
            slug=slug,
            is_platform_default=True,
            default_markup_percentage=Decimal(markup),
            fixed_margin=Decimal("0.000"),
            is_active=True,
        )
        return flagship

    changed = []
    if not flagship.is_platform_default:
        flagship.is_platform_default = True
        changed.append("is_platform_default")
    if flagship.default_markup_percentage != Decimal(markup):
        flagship.default_markup_percentage = Decimal(markup)
        changed.append("default_markup_percentage")
    if not flagship.is_active:
        flagship.is_active = True
        changed.append("is_active")
    if changed:
        flagship.save(update_fields=changed)
    return flagship


def make_store(name="Boutique Test", slug="boutique-test", owner=None, markup="25.00"):
    """Create a vendor sub-store (the slug is unique per test run)."""
    base = slug
    slug = base
    index = 2
    while Store.objects.filter(slug=slug).exists():
        slug = f"{base}-{index}"
        index += 1
    return Store.objects.create(
        name=name,
        slug=slug,
        owner=owner,
        default_markup_percentage=Decimal(markup),
        fixed_margin=Decimal("0.000"),
        is_active=True,
    )


def make_pool_product(
    title="Produit du pool",
    cost="100.000",
    category=None,
    supplier=None,
    stock=5,
    is_active=True,
):
    """Create a product in the central scraped pool."""
    if category is None:
        category, _ = Category.objects.get_or_create(
            name="Informatique", slug="informatique"
        )
    if supplier is None:
        supplier, _ = Supplier.objects.get_or_create(name="Tunisianet")
    rule, _ = MarginRule.objects.get_or_create(
        name="Default", markup_percent=Decimal("10.00"), fixed_margin_fee=Decimal("0.000")
    )
    return Product.objects.create(
        category=category,
        supplier=supplier,
        margin_rule=rule,
        title=title,
        raw_cost=Decimal(cost),
        markup_percent=Decimal("10.00"),
        fixed_margin_fee=Decimal("0.000"),
        currency="TND",
        currency_rate=Decimal("1"),
        stock=stock,
        is_active=is_active,
    )


def make_store_product(
    store,
    title="Produit de test",
    cost="100.000",
    selling_price=None,
    category="Informatique",
    source=None,
    published=True,
    in_stock=True,
    native=False,
    featured=False,
    priority=0,
):
    """Create a product in the catalogue of one store.

    ``selling_price`` defaults to the store price computed from the cost,
    which is what the application does in real life.
    """
    product = StoreProduct(
        store=store,
        scraped_source_product=source,
        title=title,
        description=f"Description de {title}",
        category=category,
        source_cost=Decimal(cost),
        in_stock=in_stock,
        is_published=published,
        is_store_native=native,
        is_featured_on_main=featured,
        featured_priority=priority,
    )
    if selling_price is not None:
        product.selling_price = Decimal(selling_price)
    product.save()
    return product
