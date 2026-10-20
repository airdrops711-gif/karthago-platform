"""Tests for the cart views (add / update / remove).

These are HTMX endpoints: the views are exercised directly with a POST,
the same way the browser does. The cart is scoped to a tenant: a visitor
on a sub-store never adds a flagship product.
"""
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from apps.catalog.tests.factories import make_flagship, make_store, make_store_product
from apps.orders.models import Cart


class CartViewTest(TestCase):
    def setUp(self):
        self.flagship = make_flagship()
        self.product = make_store_product(
            self.flagship, title="Ordinateur portable", cost="100.000"
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
        # 100.000 with the flagship 10% markup = 110.000 per unit.
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
        self.assertTrue(Cart.objects.filter(pk=cart_item.pk).exists())


class CartTenantIsolationTest(TestCase):
    """A cart never mixes two tenants."""

    def setUp(self):
        self.flagship = make_flagship()
        self.store = make_store(name="Boutique Verte", slug="boutique-verte")
        self.flagship_product = make_store_product(
            self.flagship, title="Produit flagship"
        )
        self.store_product = make_store_product(
            self.store, title="Produit boutique"
        )

    def test_substore_cannot_add_a_flagship_product(self):
        # The visitor browses the sub-store: the cart belongs to that
        # tenant, so a flagship product is out of reach.
        self.client.get(reverse("catalog:substore_home", args=[self.store.slug]))
        response = self.client.post(
            reverse("orders:add_to_cart", args=[self.flagship_product.id]),
            {"quantity": 1},
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(Cart.objects.count(), 0)

    def test_flagship_cannot_add_a_substore_product(self):
        # The visitor is on the flagship: a vendor product is out of reach.
        self.client.get(reverse("catalog:home"))
        response = self.client.post(
            reverse("orders:add_to_cart", args=[self.store_product.id]),
            {"quantity": 1},
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(Cart.objects.count(), 0)

    def test_substore_cart_holds_only_its_own_rows(self):
        self.client.get(reverse("catalog:substore_home", args=[self.store.slug]))
        self.client.post(
            reverse("orders:add_to_cart", args=[self.store_product.id]),
            {"quantity": 1},
        )
        cart = Cart.objects.first()
        self.assertIsNotNone(cart)
        self.assertEqual(cart.store, self.store)
        self.assertEqual(cart.product, self.store_product)
