"""Index the catalogue of the platform in Meilisearch.

The index holds every tenant's catalogue, and each document carries the
store it belongs to, so a search never crosses the tenant boundary.

Usage::

    python manage.py index_search                # every published product
    python manage.py index_search --store karthago
    python manage.py index_search --reconfigure  # apply the index settings
"""
from django.core.management.base import BaseCommand

from apps.catalog.models import Store
from apps.catalog.search import (
    INDEX_NAME,
    configure_index,
    create_index,
    index_store,
)


class Command(BaseCommand):
    help = "Index the tenant catalogues in Meilisearch."

    def add_arguments(self, parser):
        parser.add_argument(
            "--store",
            dest="store",
            default="",
            help="Slug of a single store to index (default: every store).",
        )
        parser.add_argument(
            "--reconfigure",
            action="store_true",
            dest="reconfigure",
            help="Apply the multi-tenant settings to the index first.",
        )

    def handle(self, *args, **options):
        self.stdout.write(f"Index: {INDEX_NAME}")

        if options["reconfigure"]:
            create_index()
            body = configure_index()
            if body is None:
                self.stderr.write(
                    "Meilisearch est injoignable — vérifiez MEILISEARCH_HOST."
                )
                return
            self.stdout.write("Paramètres de l'index appliqués.")

        slug = (options.get("store") or "").strip()
        if slug:
            store = Store.objects.filter(slug=slug).first()
            if store is None:
                self.stderr.write(f"Boutique inconnue : {slug}")
                return
            sent = index_store(store)
            self.stdout.write(f"{sent} document(s) indexé(s) pour {store.name}.")
            return

        # Every store, flagship included.
        total = 0
        for store in Store.objects.all():
            total += index_store(store)
        self.stdout.write(f"{total} document(s) indexé(s) au total.")
