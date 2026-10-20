"""Seed a vendor tenant populated from the central scraped pool.

The multi-tenant console is only meaningful once a second store exists:
without a vendor tenant the tenant management, the curation and the
ranking have nothing to manage. This command creates a vendor store and
clones a slice of the central pool into it, so the storefront at
``/s/<slug>/`` is immediately real.

It is idempotent: re-running it updates the same store and tops up its
catalogue instead of creating duplicates.

Run:  python manage.py seed_tenant --name "Boutique Tunisienne" \
          --slug boutique-tunisienne --products 24
"""
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils.text import slugify

from apps.catalog.models import Product, Store, StoreProduct
from apps.catalog.tenancy import flagship_store


class Command(BaseCommand):
    help = "Create (or top up) a vendor tenant seeded from the central pool."

    def add_arguments(self, parser):
        parser.add_argument(
            "--name", default="Boutique Tunisienne",
            help="Display name of the vendor store.",
        )
        parser.add_argument(
            "--slug", default="",
            help="URL slug. Derived from the name when omitted.",
        )
        parser.add_argument(
            "--products", type=int, default=24,
            help="Number of products to clone into the tenant catalogue.",
        )
        parser.add_argument(
            "--markup", default="30.00",
            help="Default markup percentage of the tenant, in percent.",
        )
        parser.add_argument(
            "--tagline", default="Les meilleurs prix de Tunis",
            help="Marketing line shown on the tenant homepage.",
        )
        parser.add_argument(
            "--owner", default="",
            help="Username of the staff account owning the store.",
        )
        parser.add_argument(
            "--inactive", action="store_true",
            help="Create the store offline (not reachable from the storefront).",
        )

    def handle(self, *args, **options):
        name = options["name"].strip()
        slug = (options["slug"].strip() or slugify(name))[:180]
        wanted = max(0, options["products"])

        flagship = flagship_store()
        if flagship is None:
            self.stderr.write(
                self.style.ERROR(
                    "No flagship store found. Run the migrations first."
                )
            )
            return

        owner = None
        if options["owner"]:
            from django.contrib.auth import get_user_model

            owner = get_user_model().objects.filter(
                username=options["owner"]
            ).first()
            if owner is None:
                self.stderr.write(
                    self.style.ERROR(
                        f"Unknown owner '{options['owner']}'."
                    )
                )
                return

        store, created = Store.objects.get_or_create(
            slug=slug,
            defaults={
                "name": name,
                "tagline": options["tagline"],
                "default_markup_percentage": Decimal(options["markup"]),
                "is_active": not options["inactive"],
                "is_platform_default": False,
                "owner": owner,
            },
        )
        if not created:
            store.name = name
            store.tagline = options["tagline"]
            store.default_markup_percentage = Decimal(options["markup"])
            store.is_active = not options["inactive"]
            if owner is not None:
                store.owner = owner
            store.save()

        with transaction.atomic():
            cloned = self._top_up(store, wanted)

        self.stdout.write(self.style.SUCCESS(
            f"{'Created' if created else 'Updated'} store '{store.name}' "
            f"(slug={store.slug}, id={store.id})"
        ))
        self.stdout.write(f"  storefront : {store.storefront_url}")
        self.stdout.write(f"  products   : {cloned} newly cloned")
        self.stdout.write(
            f"  catalogue  : {store.store_products.count()} products total"
        )

    def _top_up(self, store, wanted):
        """Clone pool products into the tenant catalogue, up to ``wanted``.

        A tenant product keeps the link to the pool product it was cloned
        from, so the origin stays traceable and the clone is idempotent.
        """
        if not wanted:
            return 0

        existing = set(
            StoreProduct.objects.filter(store=store)
            .exclude(scraped_source_product__isnull=True)
            .values_list("scraped_source_product_id", flat=True)
        )

        pool = (
            Product.objects.filter(is_active=True)
            .exclude(pk__in=existing)
            .order_by("-created_at")
        )

        cloned = 0
        for product in pool[:wanted]:
            images = [img.image for img in product.images.all() if img.image]
            title = product.title[:300]
            description = product.description or title
            category = product.category.name if product.category else ""

            entry = StoreProduct(
                store=store,
                scraped_source_product=product,
                title=title,
                description=description,
                category=category,
                source_cost=product.raw_cost,
                selling_price=product.retail_price,
                image_url=images[0] if images else "",
                image_urls=images,
                external_url=product.source,
                in_stock=product.stock > 0,
                is_published=True,
                is_store_native=False,
            )
            entry.save()
            cloned += 1

        return cloned
