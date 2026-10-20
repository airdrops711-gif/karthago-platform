"""Tests for the catalog views.

The storefront is tenant-scoped: the flagship at the root, the vendor
sub-stores under /s/<slug>/. A product of one store must never appear in
the catalogue of another one.
"""
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from apps.catalog.models import Category, Product, Store, StoreProduct
from apps.catalog.tests.factories import (
    make_flagship,
    make_pool_product,
    make_store,
    make_store_product,
)


class FlagshipStorefrontTest(TestCase):
    """The flagship catalogue, served from the tenant catalogue."""

    def setUp(self):
        self.flagship = make_flagship()
        self.product = make_store_product(
            self.flagship, title="Produit de test", cost="100.000"
        )
        self.hidden = make_store_product(
            self.flagship,
            title="Produit masque",
            cost="50.000",
            published=False,
        )

    def test_home_page_renders(self):
        response = self.client.get(reverse("catalog:home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Produit de test")

    def test_catalogue_renders(self):
        response = self.client.get(reverse("catalog:product_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Produit de test")

    def test_catalogue_hides_unpublished_products(self):
        response = self.client.get(reverse("catalog:product_list"))
        self.assertNotContains(response, "Produit masque")

    def test_catalogue_pagination(self):
        response = self.client.get(reverse("catalog:product_list"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("page_obj", response.context)

    def test_product_detail_view(self):
        response = self.client.get(
            reverse("catalog:product_detail", args=[self.product.id])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Produit de test")

    def test_product_detail_unpublished_404(self):
        response = self.client.get(
            reverse("catalog:product_detail", args=[self.hidden.id])
        )
        self.assertEqual(response.status_code, 404)

    def test_category_page_renders(self):
        response = self.client.get(reverse("catalog:category_detail", args=["informatique"]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Produit de test")

    def test_category_page_unknown_slug_renders_empty(self):
        # An unknown category is not an error: it simply has no product.
        response = self.client.get(reverse("catalog:category_detail", args=["inconnu"]))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Produit de test")

    def test_search_only_returns_published_products(self):
        response = self.client.get(reverse("catalog:search"), {"q": "Produit"})
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Produit masque")
        self.assertContains(response, "Produit de test")

    def test_search_with_empty_query_returns_no_result(self):
        response = self.client.get(reverse("catalog:search"), {"q": ""})
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Produit de test")


class PriorityRankingTest(TestCase):
    """The flagship ranking: curated first, then native, then imported."""

    def setUp(self):
        self.flagship = make_flagship()
        self.imported = make_store_product(
            self.flagship, title="Produit importe", native=False
        )
        self.native = make_store_product(
            self.flagship, title="Produit natif", native=True
        )
        self.curated = make_store_product(
            self.flagship,
            title="Produit curate",
            native=True,
            featured=True,
            priority=10,
        )

    def test_display_rank_is_persisted(self):
        self.assertEqual(self.curated.display_rank, 0)
        self.assertEqual(self.native.display_rank, 1)
        self.assertEqual(self.imported.display_rank, 2)

    def test_flagship_listing_is_ordered_by_priority(self):
        from apps.catalog.tenancy import flagship_listing

        titles = [p.title for p in flagship_listing(self.flagship)]
        self.assertEqual(titles[0], "Produit curate")
        self.assertEqual(titles[1], "Produit natif")
        self.assertEqual(titles[2], "Produit importe")

    def test_sub_store_listing_ignores_the_flagship_curation(self):
        from apps.catalog.tenancy import sub_store_listing

        titles = [p.title for p in sub_store_listing(self.flagship)]
        # A sub-store never shows the flagship's curation: the native
        # inventory comes first, then the imports.
        self.assertEqual(titles[0], "Produit natif")
        self.assertEqual(titles[1], "Produit importe")
        self.assertEqual(titles[2], "Produit curate")

    def test_featured_showcase_returns_only_curated(self):
        from apps.catalog.tenancy import featured_showcase

        showcase = list(featured_showcase(self.flagship))
        self.assertEqual(len(showcase), 1)
        self.assertEqual(showcase[0].title, "Produit curate")

    def test_featured_showcase_skips_out_of_stock(self):
        from apps.catalog.tenancy import featured_showcase

        self.curated.in_stock = False
        self.curated.save()
        self.assertEqual(list(featured_showcase(self.flagship)), [])


class SubStoreStorefrontTest(TestCase):
    """The vendor sub-store storefront: strictly scoped to its tenant."""

    def setUp(self):
        self.flagship = make_flagship()
        self.store = make_store(name="Boutique Bleue", slug="boutique-bleue")
        self.own_product = make_store_product(
            self.store, title="Produit de la boutique", cost="80.000"
        )
        self.flagship_product = make_store_product(
            self.flagship, title="Produit du flagship", cost="100.000"
        )

    def test_substore_home_renders(self):
        response = self.client.get(
            reverse("catalog:substore_home", args=[self.store.slug])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Produit de la boutique")
        self.assertContains(response, "Boutique Bleue")

    def test_substore_catalogue_hides_other_tenants(self):
        response = self.client.get(
            reverse("catalog:substore_catalog", args=[self.store.slug])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Produit de la boutique")
        self.assertNotContains(response, "Produit du flagship")

    def test_substore_product_page_is_tenant_scoped(self):
        response = self.client.get(
            reverse(
                "catalog:substore_product",
                args=[self.store.slug, self.own_product.id],
            )
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Produit de la boutique")

    def test_substore_product_page_refuses_another_tenant_product(self):
        response = self.client.get(
            reverse(
                "catalog:substore_product",
                args=[self.store.slug, self.flagship_product.id],
            )
        )
        self.assertEqual(response.status_code, 404)

    def test_unknown_store_slug_404(self):
        response = self.client.get(reverse("catalog:substore_home", args=["inconnu"]))
        self.assertEqual(response.status_code, 404)

    def test_inactive_store_slug_404(self):
        self.store.is_active = False
        self.store.save()
        response = self.client.get(reverse("catalog:substore_home", args=[self.store.slug]))
        self.assertEqual(response.status_code, 404)


class TenantResolutionTest(TestCase):
    """The middleware resolves exactly one tenant per request."""

    def setUp(self):
        self.flagship = make_flagship()
        self.store = make_store(name="Boutique Rouge", slug="boutique-rouge")

    def test_flagship_on_the_root(self):
        response = self.client.get(reverse("catalog:home"))
        self.assertEqual(response.context["tenant_store"], self.flagship)
        self.assertFalse(response.context["is_sub_store"])

    def test_sub_store_on_its_own_path(self):
        response = self.client.get(
            reverse("catalog:substore_home", args=[self.store.slug])
        )
        self.assertEqual(response.context["tenant_store"], self.store)
        self.assertTrue(response.context["is_sub_store"])

    def test_unknown_slug_does_not_fall_back_to_the_flagship(self):
        response = self.client.get(reverse("catalog:substore_home", args=["inconnu"]))
        self.assertEqual(response.status_code, 404)
        self.assertIsNone(response.context["tenant_store"])


class StoreModelTest(TestCase):
    """The pricing helpers of the tenant models."""

    def setUp(self):
        self.store = make_store(name="Boutique Rouge", slug="boutique-rouge", markup="25.00")

    def test_price_from_cost_uses_the_store_markup(self):
        self.assertEqual(
            self.store.price_from_cost(Decimal("100.000")), Decimal("125.000")
        )

    def test_price_from_cost_accepts_a_custom_markup(self):
        self.assertEqual(
            self.store.price_from_cost(Decimal("100.000"), Decimal("10.00")),
            Decimal("110.000"),
        )

    def test_storefront_url(self):
        flagship = make_flagship()
        self.assertEqual(flagship.storefront_url, "/")
        self.assertEqual(self.store.storefront_url, "/s/boutique-rouge/")

    def test_slug_is_generated_from_the_name(self):
        store = Store.objects.create(name="Ma Boutique Genere")
        self.assertEqual(store.slug, "ma-boutique-genere")

    def test_margin_helpers(self):
        product = make_store_product(
            self.store, title="Produit", cost="100.000", selling_price="125.000"
        )
        self.assertEqual(product.margin_amount, Decimal("25.000"))
        self.assertEqual(product.margin_percent, 20.0)

    def test_duplicate_slugs_are_suffixed(self):
        first = make_store_product(self.store, title="Produit identique")
        second = make_store_product(self.store, title="Produit identique")
        self.assertNotEqual(first.slug, second.slug)
        self.assertEqual(second.slug, f"{first.slug}-2")
