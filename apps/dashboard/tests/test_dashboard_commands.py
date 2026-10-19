"""Tests for the dashboard command centre.

The dashboard must show, for each order: the client name and phone, the
supplier of every product, the original cost and the tracking trail.
"""
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.contrib.auth.models import User

from apps.catalog.models import Category, Product, Supplier
from apps.orders.models import Customer, Order, OrderEvent, OrderItem


class DashboardCommandCentreTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(
            username="admin", email="admin@example.com", password="admin123"
        )
        self.client.login(username="admin", password="admin123")

        self.category = Category.objects.create(name="Informatique", slug="informatique")
        self.supplier = Supplier.objects.create(name="Tunisianet")
        self.product = Product.objects.create(
            category=self.category,
            supplier=self.supplier,
            title="Ordinateur portable X",
            raw_cost=Decimal("100.000"),
            markup_percent=Decimal("10.00"),
            fixed_margin_fee=Decimal("0.000"),
            currency="TND",
            currency_rate=Decimal("1"),
            source="https://www.tunisianet.com.tn/produit/42",
            stock=7,
        )
        self.customer = Customer.objects.create(
            full_name="Ahmed Ben Ali",
            phone="20123456",
            governorate="Tunis",
            address="Tunis, 10 Rue de Carthage",
        )
        self.order = Order.objects.create(
            customer=self.customer,
            total_amount=Decimal("110.000"),
            total_cost=Decimal("100.000"),
        )
        self.item = OrderItem.objects.create(
            order=self.order,
            product=self.product,
            product_title=self.product.title,
            quantity=2,
            unit_price=Decimal("110.000"),
            unit_cost=Decimal("100.000"),
            currency="TND",
            currency_rate=Decimal("1"),
            supplier_name="Tunisianet",
            source_url="https://www.tunisianet.com.tn/produit/42",
        )
        OrderEvent.objects.create(
            order=self.order,
            from_status="",
            to_status=Order.STATUS_PENDING_CONFIRMATION,
            note="Commande reçue depuis la boutique.",
            created_by="storefront",
        )

    def test_orders_list_shows_client_and_phone(self):
        response = self.client.get(reverse("dashboard:orders"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ahmed Ben Ali")
        self.assertContains(response, "20123456")

    def test_orders_list_filters_by_status(self):
        response = self.client.get(
            reverse("dashboard:orders"), {"status": Order.STATUS_PENDING_CONFIRMATION}
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "#1")

        self.order.status = Order.STATUS_SHIPPED
        self.order.save()
        response = self.client.get(
            reverse("dashboard:orders"), {"status": Order.STATUS_PENDING_CONFIRMATION}
        )
        self.assertNotContains(response, "#1")

    def test_orders_list_searches_by_phone(self):
        response = self.client.get(reverse("dashboard:orders"), {"q": "20123456"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ahmed Ben Ali")

    def test_order_detail_shows_supplier_and_original_price(self):
        response = self.client.get(
            reverse("dashboard:order_detail", args=[self.order.id])
        )
        self.assertEqual(response.status_code, 200)
        # The client details
        self.assertContains(response, "Ahmed Ben Ali")
        self.assertContains(response, "20123456")
        # The supplier and the original price
        self.assertContains(response, "Tunisianet")
        self.assertContains(response, "100.000")
        # The price charged
        self.assertContains(response, "110.000")

    def test_order_detail_shows_the_tracking_trail(self):
        response = self.client.get(
            reverse("dashboard:order_detail", args=[self.order.id])
        )
        self.assertContains(response, "Commande reçue depuis la boutique.")

    def test_update_status_creates_the_event(self):
        response = self.client.post(
            reverse("dashboard:order_update_status", args=[self.order.id]),
            {"status": Order.STATUS_CONFIRMED, "note": "Confirmé au téléphone."},
        )
        self.assertEqual(response.status_code, 302)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.STATUS_CONFIRMED)
        event = OrderEvent.objects.filter(order=self.order).first()
        self.assertEqual(event.to_status, Order.STATUS_CONFIRMED)

    def test_call_confirms_the_order(self):
        response = self.client.post(
            reverse("dashboard:order_call", args=[self.order.id]),
            {"outcome": "Client reachable"},
        )
        self.assertEqual(response.status_code, 302)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.STATUS_CONFIRMED)
        self.assertIsNotNone(self.order.confirmed_at)

    def test_note_is_recorded(self):
        response = self.client.post(
            reverse("dashboard:order_note", args=[self.order.id]),
            {"note": "Rappeler demain matin."},
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            OrderEvent.objects.filter(note="Rappeler demain matin.").exists()
        )

    def test_dashboard_requires_staff(self):
        self.client.logout()
        staff = User.objects.create_user(
            username="plain", email="plain@example.com", password="plain123"
        )
        self.client.login(username="plain", password="plain123")
        response = self.client.get(reverse("dashboard:orders"))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(staff.pk)

    def test_dashboard_requires_login(self):
        self.client.logout()
        response = self.client.get(reverse("dashboard:orders"))
        self.assertEqual(response.status_code, 302)
