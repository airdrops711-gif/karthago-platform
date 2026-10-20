"""Regression tests for the superadmin console (``/admin-dashboard/``).

Every route of the console is exercised here with a real staff
account. The console shipped with a 500 on its landing page — a missing
import in the analytics helper — and the whole test suite stayed green
because no test ever opened the console. These tests close that hole:
a broken console route is now a failing test, not a production incident.
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.catalog.models import Store, StoreProduct
from apps.catalog.tests.factories import (
    make_flagship,
    make_pool_product,
    make_store,
    make_store_product,
)
from apps.dashboard.admin_services import platform_analytics
from apps.orders.models import Customer, Order, OrderItem


class ConsoleTestCase(TestCase):
    """Base class: a staff account and a non-staff account."""

    @classmethod
    def setUpTestData(cls):
        user_model = get_user_model()
        cls.staff = user_model.objects.create_user(
            username="superadmin", password="secret-pass-123", is_staff=True
        )
        cls.plain = user_model.objects.create_user(
            username="customer", password="secret-pass-123"
        )
        cls.flagship = make_flagship()
        cls.store = make_store(name="Boutique Rouge", slug="boutique-rouge")

    def login_staff(self):
        self.client.force_login(self.staff)


class ConsoleRoutesTests(ConsoleTestCase):
    """Every console route answers 200 for a staff account."""

    def setUp(self):
        self.login_staff()
        # Give the console some data to render.
        make_store_product(self.store, title="Produit de la boutique")
        make_pool_product(title="Produit du pool")
        customer = Customer.objects.create(
            full_name="Amine Ben Salah",
            phone="+21620123456",
            governorate="Tunis",
            address="10 rue de la Liberte",
            store=self.flagship,
        )
        order = Order.objects.create(
            customer=customer,
            store=self.flagship,
            status=Order.STATUS_CONFIRMED,
            total_amount=Decimal("120.000"),
            total_cost=Decimal("80.000"),
        )
        OrderItem.objects.create(
            order=order,
            product_title="Produit vendu",
            quantity=2,
            unit_price=Decimal("60.000"),
            unit_cost=Decimal("40.000"),
        )

    def test_overview_renders(self):
        """The landing page of the console must not crash.

        This is the exact regression: a missing ``OrderItem`` import made
        ``/admin-dashboard/`` answer 500 in production.
        """
        response = self.client.get(reverse("admin_dashboard:overview"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Pilotage de la plateforme")

    def test_every_console_route_answers_200(self):
        """Sweep every route of the console in one go."""
        routes = [
            reverse("admin_dashboard:overview"),
            reverse("admin_dashboard:stores"),
            reverse("admin_dashboard:store_create"),
            reverse("admin_dashboard:store_edit", args=[self.store.id]),
            reverse("admin_dashboard:curation"),
            reverse("admin_dashboard:orders"),
            reverse("admin_dashboard:scrapers"),
            reverse("admin_dashboard:selector_sandbox"),
            reverse("admin_dashboard:central_pool"),
        ]
        for route in routes:
            with self.subTest(route=route):
                self.assertEqual(self.client.get(route).status_code, 200)

    def test_console_is_forbidden_to_anonymous_visitors(self):
        # The base class logs the staff account in: the anonymous case
        # needs a client without any session.
        self.client.logout()
        for route in [
            reverse("admin_dashboard:overview"),
            reverse("admin_dashboard:stores"),
            reverse("admin_dashboard:curation"),
        ]:
            with self.subTest(route=route):
                response = self.client.get(route)
                self.assertEqual(response.status_code, 302)
                self.assertIn("/admin/login/", response["Location"])

    def test_console_is_forbidden_to_non_staff_accounts(self):
        self.client.force_login(self.plain)
        response = self.client.get(reverse("admin_dashboard:overview"))
        self.assertEqual(response.status_code, 302)


class PlatformAnalyticsTests(ConsoleTestCase):
    """The aggregates behind the KPI cards."""

    def setUp(self):
        customer = Customer.objects.create(
            full_name="Sami Trabelsi",
            phone="+21620987654",
            governorate="Sousse",
            address="5 avenue de la Liberte",
            store=self.flagship,
        )
        self.order = Order.objects.create(
            customer=customer,
            store=self.flagship,
            status=Order.STATUS_DELIVERED_AND_PAID,
            total_amount=Decimal("100.000"),
            total_cost=Decimal("60.000"),
        )

    def test_top_product_revenue_accounts_for_the_quantity(self):
        """The revenue of a line is the unit price times the quantity.

        Summing the unit price alone ranked a product sold once above a
        product sold ten times.
        """
        OrderItem.objects.create(
            order=self.order,
            product_title="Vendu une fois",
            quantity=1,
            unit_price=Decimal("100.000"),
        )
        OrderItem.objects.create(
            order=self.order,
            product_title="Vendu dix fois",
            quantity=10,
            unit_price=Decimal("10.000"),
        )

        analytics = platform_analytics()
        top = {row["product_title"]: row for row in analytics["top_products"]}

        self.assertIn("Vendu dix fois", top)
        self.assertIn("Vendu une fois", top)
        self.assertEqual(top["Vendu dix fois"]["revenue"], Decimal("100.000"))
        self.assertEqual(top["Vendu dix fois"]["units"], 10)
        self.assertEqual(top["Vendu une fois"]["revenue"], Decimal("100.000"))
        self.assertEqual(top["Vendu une fois"]["units"], 1)

    def test_analytics_handle_a_platform_without_orders(self):
        Order.objects.all().delete()
        analytics = platform_analytics()
        self.assertEqual(analytics["total_orders"], 0)
        self.assertEqual(analytics["delivery_rate"], 0)
        self.assertEqual(analytics["top_products"], [])


class TenantManagementTests(ConsoleTestCase):
    """The superadmin creates and edits the tenants."""

    def setUp(self):
        self.login_staff()

    def test_create_a_tenant(self):
        response = self.client.post(
            reverse("admin_dashboard:store_create"),
            {
                "name": "Boutique Carthage",
                "tagline": "Le meilleur du Tunis",
                "default_markup_percentage": "35.50",
                "fixed_margin": "1.500",
                "is_active": "1",
            },
        )
        self.assertEqual(response.status_code, 302)

        store = Store.objects.get(name="Boutique Carthage")
        self.assertEqual(store.slug, "boutique-carthage")
        self.assertEqual(store.default_markup_percentage, Decimal("35.50"))
        self.assertEqual(store.fixed_margin, Decimal("1.500"))
        self.assertTrue(store.is_active)
        # A tenant is never the platform flagship.
        self.assertFalse(store.is_platform_default)
        self.assertEqual(store.storefront_url, "/s/boutique-carthage/")

    def test_create_a_tenant_without_a_name_is_rejected(self):
        response = self.client.post(
            reverse("admin_dashboard:store_create"),
            {"name": "   ", "default_markup_percentage": "20"},
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Store.objects.filter(name="   ").exists())

    def test_create_a_tenant_with_an_invalid_markup_is_rejected(self):
        response = self.client.post(
            reverse("admin_dashboard:store_create"),
            {"name": "Boutique Cassée", "default_markup_percentage": "abc"},
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Store.objects.filter(name="Boutique Cassée").exists())

    def test_the_slug_of_a_duplicate_name_is_made_unique(self):
        self.client.post(
            reverse("admin_dashboard:store_create"),
            {"name": self.store.name, "is_active": "1"},
        )
        slugs = set(Store.objects.values_list("slug", flat=True))
        self.assertIn(self.store.slug, slugs)
        self.assertEqual(len(slugs), Store.objects.count())

    def test_edit_a_tenant(self):
        response = self.client.post(
            reverse("admin_dashboard:store_edit", args=[self.store.id]),
            {
                "name": "Boutique Bleue",
                "default_markup_percentage": "42.00",
                "fixed_margin": "0.000",
                "is_active": "1",
            },
        )
        self.assertEqual(response.status_code, 302)

        self.store.refresh_from_db()
        self.assertEqual(self.store.name, "Boutique Bleue")
        self.assertEqual(self.store.default_markup_percentage, Decimal("42.00"))

    def test_edit_can_deactivate_a_tenant(self):
        self.client.post(
            reverse("admin_dashboard:store_edit", args=[self.store.id]),
            {"name": self.store.name, "default_markup_percentage": "25"},
        )
        self.store.refresh_from_db()
        self.assertFalse(self.store.is_active)

    def test_the_tenant_cannot_be_edited_by_a_non_staff_account(self):
        self.client.force_login(self.plain)
        response = self.client.post(
            reverse("admin_dashboard:store_edit", args=[self.store.id]),
            {"name": "Pirate", "default_markup_percentage": "0"},
        )
        self.assertEqual(response.status_code, 302)
        self.store.refresh_from_db()
        self.assertNotEqual(self.store.name, "Pirate")

    def test_the_flagship_can_never_be_taken_offline(self):
        """The flagship owns the root of the site.

        Deactivating it would take the whole platform down, so the
        console refuses to do it.
        """
        self.client.post(
            reverse("admin_dashboard:store_edit", args=[self.flagship.id]),
            {"name": self.flagship.name, "default_markup_percentage": "10"},
        )
        self.flagship.refresh_from_db()
        self.assertTrue(self.flagship.is_active)


class DjangoAdminTests(ConsoleTestCase):
    """The Django admin registers the models of the platform.

    The admin used to be empty: the owner logged in and found no model
    at all, with no link to the console.
    """

    def test_every_model_is_registered_in_the_django_admin(self):
        from django.contrib import admin

        registered = set(admin.site._registry)
        for model in [
            Store,
            StoreProduct,
            Customer,
            Order,
            OrderItem,
        ]:
            with self.subTest(model=model.__name__):
                self.assertIn(model, registered)

    def test_the_admin_index_lists_the_models(self):
        # The Django admin index needs a superuser, not just a staff
        # account: a plain staff member sees "no permission".
        superuser = get_user_model().objects.create_superuser(
            username="root", password="secret-pass-123", email="root@karthago.tn"
        )
        self.client.force_login(superuser)
        response = self.client.get(reverse("admin:index"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Boutiques")
        self.assertContains(response, "Commandes")

    def test_the_admin_offers_a_link_to_the_platform_console(self):
        superuser = get_user_model().objects.create_superuser(
            username="root2", password="secret-pass-123", email="root2@karthago.tn"
        )
        self.client.force_login(superuser)
        response = self.client.get(reverse("admin:index"))
        self.assertContains(response, reverse("admin_dashboard:overview"))
