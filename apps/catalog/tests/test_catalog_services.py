"""Tests for catalog services."""
from decimal import Decimal
from django.test import TestCase
from apps.catalog.services import compute_retail_price, update_product_pricing
from apps.catalog.models import Category, Supplier, MarginRule, Product


class ComputeRetailPriceTest(TestCase):
    def test_basic_computation(self):
        result = compute_retail_price(
            raw_cost=Decimal("100.000"),
            markup_percent=Decimal("30.00"),
            fixed_margin_fee=Decimal("5.000"),
        )
        expected = (Decimal("100.000") * Decimal("1.30")) + Decimal("5.000")
        self.assertEqual(result, expected)

    def test_zero_markup(self):
        result = compute_retail_price(
            raw_cost=Decimal("100.000"),
            markup_percent=Decimal("0"),
            fixed_margin_fee=Decimal("0"),
        )
        self.assertEqual(result, Decimal("100.000"))

    def test_zero_cost(self):
        result = compute_retail_price(
            raw_cost=Decimal("0"),
            markup_percent=Decimal("30.00"),
            fixed_margin_fee=Decimal("5.000"),
        )
        self.assertEqual(result, Decimal("5.000"))


class UpdateProductPricingTest(TestCase):
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
            markup_percent=Decimal("30.00"),
            fixed_margin_fee=Decimal("5.000"),
            stock=5,
        )

    def test_update_product_pricing(self):
        new_price = update_product_pricing(self.product)
        expected = (Decimal("100.000") * Decimal("1.30")) + Decimal("5.000")
        self.assertEqual(new_price, expected)
        self.product.refresh_from_db()
        self.assertEqual(self.product.retail_price, expected)
