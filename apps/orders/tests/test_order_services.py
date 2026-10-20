"""Tests for the order services and the checkout pricing.

The critical rule: the order total is always computed by the server from
the cart rows. A tampered POST must not change the price.

The cart holds ``StoreProduct`` rows since the multi-tenant migration,
so the fixture builds a flagship store and one product in it.
"""
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from apps.catalog.tests.factories import make_flagship, make_store_product
from apps.orders.models import Cart, Order, OrderEvent, OrderItem
from apps.orders.services import (
    cart_total,
    change_order_status,
    create_order_from_cart,
)


class OrderServiceTest(TestCase):
    def setUp(self):
        self.store = make_flagship()
        self.product = make_store_product(
            self.store,
            title="Ordinateur portable",
            cost="100.000",
            category="Informatique",
            source=None,
        )
        self.product.source_cost = Decimal("100.000")
        self.product.selling_price = Decimal("110.000")
        self.product.save()
        self.session_key = "test-session-key"

    def _add_to_cart(self, quantity=1, product=None):
        Cart.objects.create(
            session_key=self.session_key,
            product=product or self.product,
            store=self.store,
            quantity=quantity,
        )

    def test_cart_total_uses_retail_price(self):
        self._add_to_cart(quantity=2)
        # retail = 100 * 1.10 = 110.000
        self.assertEqual(cart_total(self.session_key), Decimal("220.000"))

    def test_create_order_from_cart_prices_server_side(self):
        self._add_to_cart(quantity=2)
        order, items = create_order_from_cart(
            self.session_key,
            full_name="Ahmed Ben Ali",
            phone="20123456",
            governorate="Tunis",
            delegation="Tunis",
            address="10 Rue de Carthage",
        )
        self.assertEqual(order.total_amount, Decimal("220.000"))
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].quantity, 2)
        self.assertEqual(items[0].unit_price, Decimal("110.000"))
        self.assertEqual(order.total_cost, Decimal("200.000"))

    def test_create_order_snapshots_supplier_and_source(self):
        self._add_to_cart()
        order, items = create_order_from_cart(
            self.session_key,
            full_name="Ahmed",
            phone="20123456",
            governorate="Tunis",
        )
        item = items[0]
        self.assertEqual(item.unit_cost, Decimal("100.000"))
        self.assertEqual(item.product_title, "Ordinateur portable")
        # The order belongs to the store that sold it.
        self.assertEqual(order.store_id, self.store.id)
        self.assertEqual(order.customer.store_id, self.store.id)

    def test_create_order_empties_the_cart(self):
        self._add_to_cart()
        create_order_from_cart(
            self.session_key,
            full_name="Ahmed",
            phone="20123456",
            governorate="Tunis",
        )
        self.assertEqual(Cart.objects.filter(session_key=self.session_key).count(), 0)

    def test_create_order_with_empty_cart_raises(self):
        with self.assertRaises(ValueError):
            create_order_from_cart(
                self.session_key,
                full_name="Ahmed",
                phone="20123456",
                governorate="Tunis",
            )

    def test_unpublished_product_is_not_orderable(self):
        self.product.is_published = False
        self.product.save()
        self._add_to_cart()
        with self.assertRaises(ValueError):
            create_order_from_cart(
                self.session_key,
                full_name="Ahmed",
                phone="20123456",
                governorate="Tunis",
            )

    def test_create_order_records_the_first_event(self):
        self._add_to_cart()
        order, _ = create_order_from_cart(
            self.session_key,
            full_name="Ahmed",
            phone="20123456",
            governorate="Tunis",
        )
        event = OrderEvent.objects.get(order=order)
        self.assertEqual(event.to_status, Order.STATUS_PENDING_CONFIRMATION)


class OrderStatusTest(TestCase):
    def setUp(self):
        from apps.orders.models import Customer

        self.store = make_flagship()
        self.customer = Customer.objects.create(
            full_name="Ahmed Ben Ali",
            phone="20123456",
            governorate="Tunis",
            address="Tunis",
            store=self.store,
        )
        self.order = Order.objects.create(
            customer=self.customer, store=self.store, total_amount=Decimal("110.000")
        )

    def test_change_status_records_the_event(self):
        change_order_status(
            self.order, Order.STATUS_CONFIRMED, note="Client confirmé."
        )
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.STATUS_CONFIRMED)
        self.assertIsNotNone(self.order.confirmed_at)
        event = OrderEvent.objects.get(order=self.order)
        self.assertEqual(event.from_status, Order.STATUS_PENDING_CONFIRMATION)
        self.assertEqual(event.to_status, Order.STATUS_CONFIRMED)

    def test_change_status_rejects_unknown_status(self):
        with self.assertRaises(ValueError):
            change_order_status(self.order, "NOT_A_STATUS")


class CheckoutViewSecurityTest(TestCase):
    """The posted total must never decide the price of the order."""

    def setUp(self):
        self.store = make_flagship()
        self.product = make_store_product(
            self.store,
            title="Television 50 pouces",
            cost="400.000",
            category="TV",
        )
        self.product.source_cost = Decimal("400.000")
        self.product.selling_price = Decimal("440.000")
        self.product.save()

    def _fill_cart(self, quantity=1):
        session = self.client.session
        session_key = session.session_key
        Cart.objects.create(
            session_key=session_key,
            product=self.product,
            store=self.store,
            quantity=quantity,
        )
        return session_key

    def test_tampered_total_is_ignored(self):
        self._fill_cart()
        response = self.client.post(
            reverse("orders:checkout"),
            {
                "full_name": "Ahmed Ben Ali",
                "phone": "20123456",
                "governorate": "Tunis",
                "delegation": "Tunis",
                "address": "10 Rue de Carthage",
                # A customer tries to buy a 440 DT TV for 1 DT.
                "total_amount": "1.000",
            },
        )
        self.assertEqual(response.status_code, 302)
        order = Order.objects.get()
        # 400 * 1.10 = 440.000
        self.assertEqual(order.total_amount, Decimal("440.000"))

    def test_invalid_phone_is_rejected(self):
        self._fill_cart()
        response = self.client.post(
            reverse("orders:checkout"),
            {
                "full_name": "Ahmed",
                "phone": "123",
                "governorate": "Tunis",
                "delegation": "Tunis",
                "address": "Tunis",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Order.objects.count(), 0)

    def test_checkout_creates_the_order_items(self):
        self._fill_cart(quantity=2)
        self.client.post(
            reverse("orders:checkout"),
            {
                "full_name": "Ahmed Ben Ali",
                "phone": "20123456",
                "governorate": "Tunis",
                "delegation": "Tunis",
                "address": "Tunis",
            },
        )
        order = Order.objects.get()
        items = OrderItem.objects.filter(order=order)
        self.assertEqual(items.count(), 1)
        item = items.first()
        self.assertEqual(item.quantity, 2)
        self.assertEqual(item.unit_price, Decimal("440.000"))

    def test_checkout_clears_the_cart(self):
        self._fill_cart()
        self.client.post(
            reverse("orders:checkout"),
            {
                "full_name": "Ahmed",
                "phone": "20123456",
                "governorate": "Tunis",
                "delegation": "Tunis",
                "address": "Tunis",
            },
        )
        self.assertEqual(Cart.objects.count(), 0)

    def test_checkout_page_renders_with_a_cart(self):
        self._fill_cart(quantity=2)
        response = self.client.get(reverse("orders:checkout"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Television 50 pouces")
        self.assertContains(response, "880.000")

    def test_checkout_page_renders_with_an_empty_cart(self):
        response = self.client.get(reverse("orders:checkout"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Votre panier est vide")


class SupplierDisplayTest(TestCase):
    """The command sheet must show a readable brand, not a source key."""

    def _item(self, supplier_name):
        return OrderItem(
            product_title="Produit",
            quantity=1,
            unit_price=Decimal("110.000"),
            unit_cost=Decimal("100.000"),
            supplier_name=supplier_name,
        )

    def test_source_key_is_rendered_as_a_brand(self):
        self.assertEqual(
            self._item("tunisianet_ordinateurs_portables").supplier_display,
            "Tunisianet",
        )
        self.assertEqual(self._item("twenty_sacs").supplier_display, "Twenty")
        self.assertEqual(self._item("noonclo_catalogue").supplier_display, "Noonclo")
        self.assertEqual(self._item("wamia_mode").supplier_display, "Wamia")

    def test_unknown_source_is_fallback_to_a_readable_name(self):
        self.assertEqual(self._item("other_shop").supplier_display, "Other Shop")

    def test_empty_supplier_is_not_blank(self):
        self.assertEqual(self._item("").supplier_display, "Fournisseur inconnu")
