"""Tests for the order services and the checkout pricing.

The critical rule: the order total is always computed by the server from
the cart rows. A tampered POST must not change the price.
"""
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from apps.catalog.models import Category, Product, Supplier
from apps.orders.models import Cart, Order, OrderEvent, OrderItem
from apps.orders.services import (
    cart_total,
    change_order_status,
    create_order_from_cart,
)


class OrderServiceTest(TestCase):
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
            currency="TND",
            currency_rate=Decimal("1"),
            source="https://www.tunisianet.com.tn/produit/1",
            stock=5,
        )
        self.session_key = "test-session-key"

    def _add_to_cart(self, quantity=1, product=None):
        Cart.objects.create(
            session_key=self.session_key,
            product=product or self.product,
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
        self.assertEqual(item.supplier_name, "Tunisianet")
        self.assertEqual(item.source_url, "https://www.tunisianet.com.tn/produit/1")
        self.assertEqual(item.unit_cost, Decimal("100.000"))
        # The item is linked to the product for live data, but the snapshot
        # survives a catalogue reset.
        self.assertEqual(item.product_id, self.product.id)

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

    def test_inactive_product_is_not_orderable(self):
        self.product.is_active = False
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

        self.customer = Customer.objects.create(
            full_name="Ahmed Ben Ali",
            phone="20123456",
            governorate="Tunis",
            address="Tunis",
        )
        self.order = Order.objects.create(
            customer=self.customer, total_amount=Decimal("110.000")
        )

    def test_change_status_records_the_event(self):
        change_order_status(
            self.order, Order.STATUS_CONFIRMED, note="Client confirm&eacute;."
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
        self.category = Category.objects.create(name="TV", slug="tv")
        self.supplier = Supplier.objects.create(name="Twenty")
        self.product = Product.objects.create(
            category=self.category,
            supplier=self.supplier,
            title="Television 50 pouces",
            raw_cost=Decimal("400.000"),
            markup_percent=Decimal("10.00"),
            fixed_margin_fee=Decimal("0.000"),
            stock=3,
        )

    def test_tampered_total_is_ignored(self):
        session = self.client.session
        session_key = session.session_key
        Cart.objects.create(
            session_key=session_key, product=self.product, quantity=1
        )
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
        session = self.client.session
        Cart.objects.create(
            session_key=session.session_key, product=self.product, quantity=1
        )
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
        session = self.client.session
        Cart.objects.create(
            session_key=session.session_key, product=self.product, quantity=2
        )
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
        self.assertEqual(item.supplier_name, "Twenty")
        self.assertEqual(item.unit_price, Decimal("440.000"))

    def test_checkout_clears_the_cart(self):
        session = self.client.session
        Cart.objects.create(
            session_key=session.session_key, product=self.product, quantity=1
        )
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
        session = self.client.session
        Cart.objects.create(
            session_key=session.session_key, product=self.product, quantity=2
        )
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
