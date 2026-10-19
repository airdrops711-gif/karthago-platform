"""Tests for orders models."""
from django.test import TestCase
from decimal import Decimal
from apps.orders.models import Customer, Order, OrderItem, Delivery
from apps.orders.constants import TUNISIAN_GOVERNORATES


class GovernoratesTest(TestCase):
    def test_24_governorates(self):
        self.assertEqual(len(TUNISIAN_GOVERNORATES), 24)
        governorate_names = [g[0] for g in TUNISIAN_GOVERNORATES]
        self.assertIn("Tunis", governorate_names)
        self.assertIn("Sfax", governorate_names)
        self.assertIn("Ariana", governorate_names)


class CustomerModelTest(TestCase):
    def test_create_customer(self):
        customer = Customer.objects.create(
            full_name="Ahmed Ben Ali",
            phone="+216 20 123 456",
            email="ahmed@example.com",
            governorate="Tunis",
            address="10 Rue de Carthage, Tunis",
        )
        self.assertEqual(str(customer), "Ahmed Ben Ali")
        self.assertEqual(customer.governorate, "Tunis")


class OrderModelTest(TestCase):
    def setUp(self):
        self.customer = Customer.objects.create(
            full_name="Ahmed Ben Ali",
            phone="+216 20 123 456",
            governorate="Tunis",
            address="10 Rue de Carthage, Tunis",
        )

    def test_create_order(self):
        order = Order.objects.create(
            customer=self.customer,
            total_amount=Decimal("150.000"),
            payment_method="COD",
        )
        self.assertEqual(str(order), f"Order {order.id} - Ahmed Ben Ali")
        self.assertEqual(order.status, "PENDING_CONFIRMATION")
        self.assertEqual(order.payment_method, "COD")

    def test_order_status_lifecycle(self):
        order = Order.objects.create(
            customer=self.customer,
            total_amount=Decimal("150.000"),
        )
        self.assertEqual(order.status, "PENDING_CONFIRMATION")
        order.status = "CONFIRMED"
        order.save()
        self.assertEqual(order.status, "CONFIRMED")
        order.status = "DELIVERED_AND_PAID"
        order.save()
        self.assertEqual(order.status, "DELIVERED_AND_PAID")


class OrderItemModelTest(TestCase):
    def setUp(self):
        self.customer = Customer.objects.create(
            full_name="Ahmed Ben Ali",
            phone="+216 20 123 456",
            governorate="Tunis",
            address="10 Rue de Carthage, Tunis",
        )
        self.order = Order.objects.create(
            customer=self.customer,
            total_amount=Decimal("150.000"),
        )

    def test_order_item_line_total(self):
        item = OrderItem.objects.create(
            order=self.order,
            product_title="iPhone 15",
            quantity=2,
            unit_price=Decimal("750.000"),
        )
        self.assertEqual(item.line_total(), Decimal("1500.000"))

    def test_order_item_str(self):
        item = OrderItem.objects.create(
            order=self.order,
            product_title="iPhone 15",
            quantity=2,
            unit_price=Decimal("750.000"),
        )
        self.assertEqual(str(item), "2x iPhone 15")


class DeliveryModelTest(TestCase):
    def setUp(self):
        self.customer = Customer.objects.create(
            full_name="Ahmed Ben Ali",
            phone="+216 20 123 456",
            governorate="Tunis",
            address="10 Rue de Carthage, Tunis",
        )
        self.order = Order.objects.create(
            customer=self.customer,
            total_amount=Decimal("150.000"),
        )

    def test_create_delivery(self):
        delivery = Delivery.objects.create(
            order=self.order,
            tracking_number="TN123456",
            paid_on_delivery=True,
        )
        self.assertEqual(str(delivery), f"Delivery for Order {self.order.id}")
        self.assertTrue(delivery.paid_on_delivery)
