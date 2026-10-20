"""Regression tests for the storefront rendering bugs.

1. The cart must appear ONCE per page (the nav was rendered twice on the
   order page, and the navbar carried two overlapping cart badges).
2. The SEO endpoints must serve valid robots.txt and sitemap.xml.

The catalogue is the tenant one since the multi-tenant migration, so the
fixtures build a flagship store and its ``StoreProduct`` rows.
"""
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from apps.catalog.tests.factories import make_flagship, make_store_product
from apps.orders.models import Customer, Order


class SingleCartPerPageTest(TestCase):
    """The nav (and its cart badge) must be rendered exactly once."""

    def setUp(self):
        self.flagship = make_flagship()
        self.product = make_store_product(
            self.flagship,
            title="Television",
            cost="100.000",
            category="TV",
        )
        self.customer = Customer.objects.create(
            full_name="Ahmed", phone="20123456", governorate="Tunis", address="Tunis",
            store=self.flagship,
        )
        self.order = Order.objects.create(
            customer=self.customer, store=self.flagship, total_amount=Decimal("110.000")
        )

    def test_order_detail_renders_the_nav_once(self):
        response = self.client.get(
            reverse("orders:order_detail", args=[self.order.id])
        )
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        # One <nav> element: the order page used to include nav.html on
        # top of base.html, which rendered the whole navbar twice.
        self.assertEqual(content.count("<nav"), 1)
        # Exactly two cart badges: one in the desktop navbar, one in the
        # mobile navbar. They live in mutually exclusive breakpoints.
        self.assertEqual(content.count("data-cart-badge"), 2)
        # The floating cart overlay that duplicated the navbar cart is gone.
        self.assertNotIn("absolute top-3 right-4", content)

    def test_home_page_renders_the_nav_once(self):
        response = self.client.get(reverse("catalog:home"))
        content = response.content.decode()
        self.assertEqual(content.count("<nav"), 1)
        self.assertEqual(content.count("data-cart-badge"), 2)
        self.assertNotIn("absolute top-3 right-4", content)

    def test_cart_page_renders_the_nav_once(self):
        response = self.client.get(reverse("orders:cart"))
        content = response.content.decode()
        self.assertEqual(content.count("<nav"), 1)
        self.assertEqual(content.count("data-cart-badge"), 2)
        self.assertNotIn("absolute top-3 right-4", content)

    def test_catalog_page_renders_the_nav_once(self):
        response = self.client.get(reverse("catalog:product_list"))
        content = response.content.decode()
        self.assertEqual(content.count("<nav"), 1)
        self.assertEqual(content.count("data-cart-badge"), 2)


class SeoEndpointTest(TestCase):
    def setUp(self):
        self.flagship = make_flagship()

    def test_robots_txt(self):
        response = self.client.get(reverse("seo:robots"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/plain")
        body = response.content.decode()
        self.assertIn("User-agent: *", body)
        self.assertIn("Disallow: /admin/", body)
        self.assertIn("Sitemap:", body)

    def test_sitemap_xml(self):
        response = self.client.get(reverse("seo:sitemap"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("application/xml", response["Content-Type"])
        body = response.content.decode()
        self.assertIn("<urlset", body)
        self.assertIn("<loc>", body)

    def test_sitemap_lists_the_catalogue(self):
        make_store_product(
            self.flagship, title="Television", cost="100.000", category="TV"
        )
        response = self.client.get(reverse("seo:sitemap"))
        body = response.content.decode()
        self.assertIn("/catalogue/", body)
        self.assertIn("/category/tv/", body)

    def test_product_page_has_product_jsonld(self):
        product = make_store_product(
            self.flagship,
            title="Television 50 pouces",
            cost="100.000",
            category="TV",
        )
        response = self.client.get(
            reverse("catalog:product_detail", args=[product.id])
        )
        body = response.content.decode()
        self.assertIn('"@type": "Product"', body)
        self.assertIn("priceCurrency", body)
        self.assertIn("InStock", body)

    def test_home_page_has_meta_description(self):
        response = self.client.get(reverse("catalog:home"))
        body = response.content.decode()
        self.assertIn('name="description"', body)
        self.assertIn('property="og:title"', body)
        self.assertIn('rel="canonical"', body)
