"""Purge the catalogue and the supplier sources.

Used to reset the storefront to a new, verified supplier set:

    python manage.py purge_catalog --sources --categories

Every step is opt-in through a flag so a plain `purge_catalog` only clears
the products.
"""
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.catalog.models import Product, ProductImage, Category, Supplier
from apps.scraper.models import ScrapedSource, ScraperLog


class Command(BaseCommand):
    help = "Delete products, sources, categories and suppliers from the catalogue."

    def add_arguments(self, parser):
        parser.add_argument(
            "--products",
            action="store_true",
            help="Delete every product (and its images).",
        )
        parser.add_argument(
            "--sources",
            action="store_true",
            help="Delete every scraped source and its logs.",
        )
        parser.add_argument(
            "--categories",
            action="store_true",
            help="Delete every category.",
        )
        parser.add_argument(
            "--suppliers",
            action="store_true",
            help="Delete every supplier.",
        )
        parser.add_argument(
            "--all",
            action="store_true",
            help="Delete products, sources, categories and suppliers.",
        )

    def handle(self, *args, **options):
        if options.get("all"):
            options["products"] = True
            options["sources"] = True
            options["categories"] = True
            options["suppliers"] = True

        if not any(
            options.get(key)
            for key in ("products", "sources", "categories", "suppliers")
        ):
            self.stdout.write(
                self.style.WARNING(
                    "Nothing to do. Pass --products, --sources, --categories, "
                    "--suppliers or --all."
                )
            )
            return

        with transaction.atomic():
            if options.get("products"):
                images = ProductImage.objects.all().delete()
                products = Product.objects.all().delete()
                self.stdout.write(
                    self.style.SUCCESS(
                        f"  deleted {products[0]} products, {images[0]} images"
                    )
                )

            if options.get("sources"):
                logs = ScraperLog.objects.all().delete()
                sources = ScrapedSource.objects.all().delete()
                self.stdout.write(
                    self.style.SUCCESS(
                        f"  deleted {sources[0]} sources, {logs[0]} logs"
                    )
                )

            if options.get("categories"):
                # Products must be gone first (FK SET_NULL would leave
                # orphan products pointing at a deleted category).
                orphans = Product.objects.filter(category__isnull=False).count()
                if orphans:
                    self.stdout.write(
                        self.style.WARNING(
                            f"  {orphans} products still reference a category; "
                            "delete the products first"
                        )
                    )
                else:
                    deleted = Category.objects.all().delete()
                    self.stdout.write(
                        self.style.SUCCESS(f"  deleted {deleted[0]} categories")
                    )

            if options.get("suppliers"):
                orphans = Product.objects.filter(supplier__isnull=False).count()
                if orphans:
                    self.stdout.write(
                        self.style.WARNING(
                            f"  {orphans} products still reference a supplier; "
                            "delete the products first"
                        )
                    )
                else:
                    deleted = Supplier.objects.all().delete()
                    self.stdout.write(
                        self.style.SUCCESS(f"  deleted {deleted[0]} suppliers")
                    )

        self.stdout.write(self.style.SUCCESS("Purge complete."))
