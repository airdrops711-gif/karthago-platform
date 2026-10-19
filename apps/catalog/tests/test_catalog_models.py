"""Tests for catalog models."""
from decimal import Decimal
from django.test import TestCase
from django.core.exceptions import ValidationError
from apps.catalog.models import Category, Supplier, MarginRule, Product


class CategoryModelTest(TestCase):
    def test_create_category(self):
        category = Category.objects.create(
            name="Electronics", slug="electronics", description="Electronic devices"
        )
        self.assertEqual(str(category), "Electronics")
        self.assertEqual(category.slug, "electronics")

    def test_category_slug_unique(self):
        Category.objects.create(name="Electronics", slug="electronics")
        with self.assertRaises(Exception):
            Category.objects.create(name="Electronics", slug="electronics")


class SupplierModelTest(TestCase):
    def test_create_supplier(self):
        supplier = Supplier.objects.create(
            name="Tech Supplier",
            website="https://example.com",
            contact_email="contact@example.com",
        )
        self.assertEqual(str(supplier), "Tech Supplier")
        self.assertTrue(supplier.is_active)


class MarginRuleModelTest(TestCase):
    def test_create_margin_rule(self):
        rule = MarginRule.objects.create(
            name="Standard Markup",
            markup_percent=Decimal("30.00"),
            fixed_margin_fee=Decimal("5.000"),
        )
        self.assertEqual(str(rule), "Standard Markup")
        self.assertEqual(rule.markup_percent, Decimal("30.00"))
        self.assertEqual(rule.fixed_margin_fee, Decimal("5.000"))


class ProductModelTest(TestCase):
    def setUp(self):
        self.category = Category.objects.create(
            name="Electronics", slug="electronics"
        )
        self.supplier = Supplier.objects.create(name="Tech Supplier")
        self.margin_rule = MarginRule.objects.create(
            name="Standard", markup_percent=Decimal("30.00"), fixed_margin_fee=Decimal("5.000")
        )

    def test_create_product(self):
        product = Product.objects.create(
            category=self.category,
            supplier=self.supplier,
            margin_rule=self.margin_rule,
            title="iPhone 15",
            description="Latest iPhone",
            raw_cost=Decimal("100.000"),
            markup_percent=Decimal("30.00"),
            fixed_margin_fee=Decimal("5.000"),
            stock=10,
        )
        self.assertEqual(str(product), "iPhone 15")
        self.assertEqual(product.stock, 10)
        self.assertTrue(product.is_active)

    def test_compute_retail_price(self):
        product = Product(
            category=self.category,
            supplier=self.supplier,
            margin_rule=self.margin_rule,
            title="Test Product",
            raw_cost=Decimal("100.000"),
            markup_percent=Decimal("30.00"),
            fixed_margin_fee=Decimal("5.000"),
        )
        expected = (Decimal("100.000") * (1 + Decimal("30.00") / Decimal("100"))) + Decimal("5.000")
        self.assertEqual(product.compute_retail_price(), expected)

    def test_save_computes_retail_price(self):
        product = Product.objects.create(
            category=self.category,
            supplier=self.supplier,
            margin_rule=self.margin_rule,
            title="Test Product",
            raw_cost=Decimal("100.000"),
            markup_percent=Decimal("30.00"),
            fixed_margin_fee=Decimal("5.000"),
            stock=5,
        )
        expected = (Decimal("100.000") * (1 + Decimal("30.00") / Decimal("100"))) + Decimal("5.000")
        self.assertEqual(product.retail_price, expected)

    def test_product_negative_cost_invalid(self):
        with self.assertRaises(ValidationError):
            product = Product(
                category=self.category,
                supplier=self.supplier,
                margin_rule=self.margin_rule,
                title="Invalid Product",
                raw_cost=Decimal("-10.000"),
            )
            product.full_clean()

    def test_product_stays_active_when_out_of_stock(self):
        """Stock and visibility are independent.

        A supplier that does not publish a stock figure still has a live
        product, so the scraper keeps it visible and the storefront shows a
        "Rupture" badge instead of hiding it. Only the scraper decides
        visibility, through the explicit is_active flag.
        """
        product = Product.objects.create(
            category=self.category,
            supplier=self.supplier,
            margin_rule=self.margin_rule,
            title="Out of Stock",
            raw_cost=Decimal("50.000"),
            stock=0,
        )
        self.assertTrue(product.is_active)
