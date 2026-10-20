"""Tests for the tenant catalogue helpers.

The central scraped pool is the raw material of the platform; the
flagship catalogue is what it actually sells. These tests check the
synchronisation between the two, and the price parsing of the bulk
importer.
"""
from decimal import Decimal

from django.test import TestCase

from apps.catalog.models import StoreProduct
from apps.catalog.product_ingestion import parse_tunisian_price
from apps.catalog.tenancy import flagship_listing, sync_flagship_product
from apps.catalog.tests.factories import (
    make_flagship,
    make_pool_product,
    make_store,
    make_store_product,
)


class FlagshipSyncTest(TestCase):
    """A scraped product always has an entry in the flagship catalogue."""

    def setUp(self):
        self.flagship = make_flagship()
        self.pool_product = make_pool_product(title="Produit scrapé", cost="100.000")

    def test_sync_creates_the_flagship_entry(self):
        entry = sync_flagship_product(self.pool_product)
        self.assertIsNotNone(entry)
        self.assertEqual(entry.store, self.flagship)
        self.assertEqual(entry.title, "Produit scrapé")
        self.assertEqual(entry.source_cost, Decimal("100.000"))
        self.assertFalse(entry.is_store_native)
        self.assertTrue(
            StoreProduct.objects.filter(
                store=self.flagship, scraped_source_product=self.pool_product
            ).exists()
        )

    def test_sync_is_idempotent(self):
        first = sync_flagship_product(self.pool_product)
        second = sync_flagship_product(self.pool_product)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(
            StoreProduct.objects.filter(
                store=self.flagship, scraped_source_product=self.pool_product
            ).count(),
            1,
        )

    def test_sync_updates_the_price(self):
        entry = sync_flagship_product(self.pool_product)
        self.pool_product.raw_cost = Decimal("150.000")
        self.pool_product.save()
        refreshed = sync_flagship_product(self.pool_product)
        self.assertEqual(refreshed.pk, entry.pk)
        self.assertEqual(refreshed.source_cost, Decimal("150.000"))

    def test_scraped_product_appears_in_the_flagship_listing(self):
        sync_flagship_product(self.pool_product)
        titles = [p.title for p in flagship_listing(self.flagship)]
        self.assertIn("Produit scrapé", titles)

    def test_a_vendor_store_is_never_touched_by_the_sync(self):
        store = make_store(name="Boutique Sync", slug="boutique-sync")
        sync_flagship_product(self.pool_product)
        self.assertEqual(StoreProduct.objects.filter(store=store).count(), 0)


class PriceParsingTest(TestCase):
    """The Tunisian price formats accepted by the bulk importer."""

    def test_comma_decimal(self):
        self.assertEqual(parse_tunisian_price("12,500"), Decimal("12.500"))

    def test_dot_thousands(self):
        self.assertEqual(parse_tunisian_price("1.299"), Decimal("1299.000"))

    def test_currency_suffix(self):
        self.assertEqual(parse_tunisian_price("45.500 DT"), Decimal("45500.000"))

    def test_plain_number(self):
        self.assertEqual(parse_tunisian_price("99"), Decimal("99.000"))

    def test_invalid_price_raises(self):
        with self.assertRaises(ValueError):
            parse_tunisian_price("pas un prix")
