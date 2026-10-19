"""Regression tests for the storefront rendering bugs.

1. The cart must appear ONCE per page (the nav was rendered twice on the
   order page, and the navbar carried two overlapping cart badges).
2. The SEO endpoints must serve valid robots.txt and sitemap.xml.
"""
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from apps.catalog.models import Category, Product, Supplier
from apps.orders.models import Customer, Order


class SingleCartPerPageTest(TestCase):
    """The nav (and its cart badge) must be rendered exactly once."""

    def setUp(self):
        self.category = Category.objects.create(name="TV", slug="tv")
        self.supplier = Supplier.objects.create(name="Twenty")
        self.product = Product.objects.create(
            category=self.category,
            supplier=self.supplier,
            title="Television",
            raw_cost=Decimal("100.000"),
            markup_percent=Decimal("10.00"),
            stock=3,
        )
        self.customer = Customer.objects.create(
            full_name="Ahmed", phone="20123456", governorate="Tunis", address="Tunis"
        )
        self.order = Order.objects.create(
            customer=self.customer, total_amount=Decimal("110.000")
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
        category = Category.objects.create(name="TV", slug="tv")
        supplier = Supplier.objects.create(name="Twenty")
        Product.objects.create(
            category=category,
            supplier=supplier,
            title="Television",
            raw_cost=Decimal("100.000"),
            stock=3,
        )
        response = self.client.get(reverse("seo:sitemap"))
        body = response.content.decode()
        self.assertIn("/catalogue/", body)
        self.assertIn("/category/tv/", body)

    def test_product_page_has_product_jsonld(self):
        category = Category.objects.create(name="TV", slug="tv")
        supplier = Supplier.objects.create(name="Twenty")
        product = Product.objects.create(
            category=category,
            supplier=supplier,
            title="Television 50 pouces",
            raw_cost=Decimal("100.000"),
            markup_percent=Decimal("10.00"),
            stock=3,
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
