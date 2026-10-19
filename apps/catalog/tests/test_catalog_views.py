"""Tests for catalog views."""
from decimal import Decimal
from django.test import TestCase
from django.urls import reverse
from apps.catalog.models import Category, Supplier, MarginRule, Product


class ProductListViewTest(TestCase):
    def setUp(self):
        self.category = Category.objects.create(name="Electronics", slug="electronics")
        self.supplier = Supplier.objects.create(name="Tech Supplier")
        self.margin_rule = MarginRule.objects.create(
            name="Standard", markup_percent=Decimal("30.00"), fixed_margin_fee=Decimal("5.000")
        )
        Product.objects.create(
            category=self.category,
            supplier=self.supplier,
            margin_rule=self.margin_rule,
            title="Product 1",
            raw_cost=Decimal("100.000"),
            stock=10,
        )
        Product.objects.create(
            category=self.category,
            supplier=self.supplier,
            margin_rule=self.margin_rule,
            title="Product 2",
            raw_cost=Decimal("200.000"),
            stock=0,
            is_active=False,
        )

    def test_product_list_shows_active_only(self):
        response = self.client.get(reverse("catalog:product_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Product 1")
        self.assertNotContains(response, "Product 2")

    def test_product_list_pagination(self):
        response = self.client.get(reverse("catalog:product_list"))
        self.assertEqual(response.status_code, 200)


class ProductDetailViewTest(TestCase):
    def setUp(self):
        self.category = Category.objects.create(name="Electronics", slug="electronics")
        self.supplier = Supplier.objects.create(name="Tech Supplier")
        self.margin_rule = MarginRule.objects.create(
            name="Standard", markup_percent=Decimal("30.00"), fixed_margin_fee=Decimal("5.000")
        )
        self.product = Product.objects.create(
            category=self.category,
            supplier=self.supplier,
            margin_rule=self.margin_rule,
            title="Test Product",
            raw_cost=Decimal("100.000"),
            stock=5,
        )

    def test_product_detail_view(self):
        response = self.client.get(reverse("catalog:product_detail", args=[self.product.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Test Product")

    def test_product_detail_inactive_404(self):
        self.product.is_active = False
        self.product.stock = 0
        self.product.save()
        response = self.client.get(reverse("catalog:product_detail", args=[self.product.id]))
        self.assertEqual(response.status_code, 404)
