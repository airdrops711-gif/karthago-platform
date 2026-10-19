"""Tests for the cart views (add / update / remove).

These are HTMX endpoints: the views are exercised directly with a POST,
the same way the browser does.
"""
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from apps.catalog.models import Category, Product, Supplier
from apps.orders.models import Cart


class CartViewTest(TestCase):
    def setUp(self):
        self.category = Category.objects.create(name="Informatique", slug="informatique")
        self.supplier = Supplier.objects.create(name="Tunisianet")
        self.product = Product.objects.create(
            category=self.category,
            supplier=self.supplier,
            title="Ordinateur portable",
            raw_cost=Decimal("100.000"),
            markup_percent=Decimal("10.00"),
            fixed_margin_fee=Decimal("0.000"),
            stock=5,
        )

    def test_add_to_cart_creates_the_row(self):
        response = self.client.post(
            reverse("orders:add_to_cart", args=[self.product.id]),
            {"quantity": 2},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Cart.objects.count(), 1)
        self.assertEqual(Cart.objects.first().quantity, 2)

    def test_add_to_cart_twice_increases_the_quantity(self):
        self.client.post(
            reverse("orders:add_to_cart", args=[self.product.id]), {"quantity": 1}
        )
        self.client.post(
            reverse("orders:add_to_cart", args=[self.product.id]), {"quantity": 3}
        )
        self.assertEqual(Cart.objects.count(), 1)
        self.assertEqual(Cart.objects.first().quantity, 4)

    def test_add_to_cart_updates_every_badge(self):
        response = self.client.post(
            reverse("orders:add_to_cart", args=[self.product.id]), {"quantity": 1}
        )
        body = response.content.decode()
        # Both the desktop and the mobile badge must be refreshed.
        self.assertIn("data-cart-badge", body)
        self.assertIn("textContent", body)

    def test_cart_page_lists_the_items(self):
        self.client.post(
            reverse("orders:add_to_cart", args=[self.product.id]), {"quantity": 2}
        )
        response = self.client.get(reverse("orders:cart"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ordinateur portable")
        self.assertContains(response, "220.000")

    def test_remove_from_cart(self):
        self.client.post(
            reverse("orders:add_to_cart", args=[self.product.id]), {"quantity": 1}
        )
        cart_item = Cart.objects.first()
        response = self.client.post(
            reverse("orders:remove_from_cart", args=[cart_item.id])
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Cart.objects.count(), 0)

    def test_update_quantity(self):
        self.client.post(
            reverse("orders:add_to_cart", args=[self.product.id]), {"quantity": 1}
        )
        cart_item = Cart.objects.first()
        response = self.client.post(
            reverse("orders:update_cart", args=[cart_item.id]), {"quantity": 5}
        )
        self.assertEqual(response.status_code, 200)
        cart_item.refresh_from_db()
        self.assertEqual(cart_item.quantity, 5)

    def test_update_quantity_to_zero_removes_the_row(self):
        self.client.post(
            reverse("orders:add_to_cart", args=[self.product.id]), {"quantity": 1}
        )
        cart_item = Cart.objects.first()
        self.client.post(
            reverse("orders:update_cart", args=[cart_item.id]), {"quantity": 0}
        )
        self.assertEqual(Cart.objects.count(), 0)

    def test_cannot_touch_another_session_cart(self):
        self.client.post(
            reverse("orders:add_to_cart", args=[self.product.id]), {"quantity": 1}
        )
        cart_item = Cart.objects.first()
        other = Cart.objects.create(
            session_key="someone-else", product=self.product, quantity=1
        )
        # The cart of another session must not be removable through the
        # regular endpoint.
        response = self.client.post(
            reverse("orders:remove_from_cart", args=[other.id])
        )
        self.assertEqual(response.status_code, 404)
        self.assertTrue(Cart.objects.filter(pk=other.pk).exists())
        self.assertTrue(cart_item.pk)
