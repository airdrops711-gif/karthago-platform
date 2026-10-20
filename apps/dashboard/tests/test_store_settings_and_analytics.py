"""Tests for the two new consoles.

* the vendor store settings (``/dashboard/store/``) — a vendor edits
  its own store identity and nothing else;
* the platform analytics plane (``/admin-dashboard/analytics/``) — the
  operator gets the whole platform in one page, outside the Django
  admin.
"""
import io
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from apps.catalog.models import Store
from apps.catalog.tests.factories import (
    make_flagship,
    make_store,
    make_store_product,
)
from apps.orders.models import Customer, Order, OrderItem


class StoreSettingsTest(TestCase):
    """A vendor edits its own store: name, logo, contacts, prices."""

    def setUp(self):
        self.user = User.objects.create_superuser(
            username="vendor", email="vendor@example.com", password="vendor123"
        )
        self.user.is_staff = True
        self.user.save()
        self.store = make_store(name="Boutique Ahmed", owner=self.user)
        self.client.login(username="vendor", password="vendor123")

    def test_the_page_renders(self):
        response = self.client.get(reverse("dashboard:store_settings"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Boutique Ahmed")
        self.assertContains(response, reverse("dashboard:store_settings"))

    def test_it_requires_a_login(self):
        self.client.logout()
        response = self.client.get(reverse("dashboard:store_settings"))
        self.assertIn(response.status_code, (302, 403))

    def test_the_vendor_can_rename_its_store(self):
        response = self.client.post(
            reverse("dashboard:store_settings"),
            {
                "name": "Boutique Ahmed Sport",
                "tagline": "Le sport au juste prix",
                "description": "Des articles de sport livrés chez vous.",
                "phone_number": "+216 20 123 456",
                "whatsapp_number": "+216 20 123 456",
                "address": "10 rue de Carthage, Tunis",
                "default_markup_percentage": "30.00",
                "fixed_margin": "2.500",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.store.refresh_from_db()
        self.assertEqual(self.store.name, "Boutique Ahmed Sport")
        self.assertEqual(self.store.tagline, "Le sport au juste prix")
        self.assertEqual(self.store.phone_number, "+216 20 123 456")
        self.assertEqual(self.store.default_markup_percentage, Decimal("30.00"))
        self.assertEqual(self.store.fixed_margin, Decimal("2.500"))

    def test_the_name_is_mandatory(self):
        response = self.client.post(
            reverse("dashboard:store_settings"),
            {"name": "   ", "default_markup_percentage": "25.00"},
        )
        self.assertEqual(response.status_code, 200)
        self.store.refresh_from_db()
        self.assertEqual(self.store.name, "Boutique Ahmed")

    def test_a_negative_margin_is_rejected(self):
        response = self.client.post(
            reverse("dashboard:store_settings"),
            {"name": "Boutique Ahmed", "default_markup_percentage": "-5"},
        )
        self.assertEqual(response.status_code, 200)
        self.store.refresh_from_db()
        self.assertEqual(self.store.default_markup_percentage, Decimal("25.00"))

    def test_a_logo_can_be_uploaded(self):
        """A real PNG is stored in the database and served by a view."""
        from PIL import Image

        buffer = io.BytesIO()
        Image.new("RGB", (64, 64), color=(217, 119, 6)).save(buffer, format="PNG")
        buffer.seek(0)

        upload = io.BytesIO(buffer.getvalue())
        upload.name = "logo.png"

        response = self.client.post(
            reverse("dashboard:store_settings"),
            {"name": "Boutique Ahmed", "logo": upload},
        )
        self.assertEqual(response.status_code, 302)
        self.store.refresh_from_db()
        self.assertEqual(self.store.logo_url, reverse("store_logo", args=[self.store.slug]))

        # The image is in the database, not in the container filesystem.
        from apps.catalog.models import StoreLogo

        logo = StoreLogo.objects.get(store=self.store)
        self.assertEqual(logo.content_type, "image/png")
        self.assertTrue(bytes(logo.image).startswith(b"\x89PNG"))

    def test_the_uploaded_logo_is_served(self):
        from PIL import Image

        from apps.catalog.models import StoreLogo

        buffer = io.BytesIO()
        Image.new("RGB", (32, 32), color=(0, 0, 0)).save(buffer, format="PNG")
        StoreLogo.objects.create(
            store=self.store,
            image=buffer.getvalue(),
            content_type="image/png",
            width=32,
            height=32,
        )

        response = self.client.get(reverse("store_logo", args=[self.store.slug]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "image/png")
        self.assertTrue(response.content.startswith(b"\x89PNG"))

    def test_a_missing_logo_answers_404(self):
        response = self.client.get(reverse("store_logo", args=[self.store.slug]))
        self.assertEqual(response.status_code, 404)

    def test_the_logo_of_an_unknown_store_answers_404(self):
        response = self.client.get(reverse("store_logo", args=["does-not-exist"]))
        self.assertEqual(response.status_code, 404)

    def test_a_logo_url_is_accepted(self):
        response = self.client.post(
            reverse("dashboard:store_settings"),
            {
                "name": "Boutique Ahmed",
                "logo_url": "https://example.com/logo.png",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.store.refresh_from_db()
        self.assertEqual(self.store.logo_url, "https://example.com/logo.png")

    def test_a_forbidden_logo_format_is_rejected(self):
        upload = io.BytesIO(b"%PDF-1.4 not an image")
        upload.name = "logo.pdf"

        response = self.client.post(
            reverse("dashboard:store_settings"),
            {"name": "Boutique Ahmed", "logo": upload},
        )
        self.assertEqual(response.status_code, 200)
        self.store.refresh_from_db()
        self.assertEqual(self.store.logo_url, "")

    def test_a_vendor_cannot_write_into_another_store(self):
        """The page always writes into the tenant of the request."""
        other = make_store(name="Boutique Autre", slug="boutique-autre")
        other_before = other.name

        self.client.post(
            reverse("dashboard:store_settings"),
            {"name": "Boutique Ahmed Piraté"},
        )

        other.refresh_from_db()
        self.assertEqual(other.name, other_before)
        self.store.refresh_from_db()
        self.assertEqual(self.store.name, "Boutique Ahmed Piraté")

    def test_the_vendor_cannot_edit_the_commission(self):
        """The commission belongs to the superadmin, not to the vendor."""
        before = self.store.commission_rate
        self.client.post(
            reverse("dashboard:store_settings"),
            {
                "name": "Boutique Ahmed",
                "commission_rate": "99",
                "commission_type": "FLAT",
            },
        )
        self.store.refresh_from_db()
        self.assertEqual(self.store.commission_rate, before)
        self.assertEqual(self.store.commission_type, "PERCENT")

    def test_a_suspended_vendor_still_reaches_its_own_page(self):
        """A suspended vendor must see its store and the reason."""
        self.store.suspend("Litige en cours")
        response = self.client.get(reverse("dashboard:store_settings"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Litige en cours")


class AnalyticsPlaneTest(TestCase):
    """The superadmin analytics plane."""

    def setUp(self):
        self.admin = User.objects.create_superuser(
            username="admin", email="admin@example.com", password="admin123"
        )
        self.client.login(username="admin", password="admin123")

        self.flagship = make_flagship()
        self.store = make_store(name="Boutique Hammamet", slug="boutique-hammamet")
        self.product = make_store_product(
            self.store, title="Ventilateur", cost="100.000", selling_price="125.000"
        )

        self.customer = Customer.objects.create(
            full_name="Sami Trabelsi",
            phone="20123456",
            governorate="Nabeul",
            address="Hammamet",
            store=self.store,
        )
        self.order = Order.objects.create(
            customer=self.customer,
            store=self.store,
            total_amount=Decimal("125.000"),
            total_cost=Decimal("100.000"),
            status=Order.STATUS_DELIVERED_AND_PAID,
        )
        OrderItem.objects.create(
            order=self.order,
            product=self.product,
            product_title=self.product.title,
            quantity=1,
            unit_price=Decimal("125.000"),
            unit_cost=Decimal("100.000"),
            currency="TND",
            currency_rate=Decimal("1"),
            supplier_name="Tunisianet",
        )

    def test_the_page_renders(self):
        response = self.client.get(reverse("admin_dashboard:analytics"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Boutique Hammamet")
        self.assertContains(response, "Ventilateur")
        self.assertContains(response, "Nabeul")

    def test_it_requires_a_staff_account(self):
        self.client.logout()
        User.objects.create_user(username="plain", password="plain123")
        self.client.login(username="plain", password="plain123")
        response = self.client.get(reverse("admin_dashboard:analytics"))
        self.assertIn(response.status_code, (302, 403))

    def test_the_kpis_count_the_platform(self):
        from apps.dashboard.analytics import platform_kpis

        kpis = platform_kpis()
        self.assertEqual(kpis["total_orders"], 1)
        self.assertEqual(kpis["delivered_orders"], 1)
        self.assertEqual(kpis["gmv"], Decimal("125.000"))
        self.assertEqual(kpis["supplier_cost"], Decimal("100.000"))
        self.assertEqual(kpis["gross_margin"], Decimal("25.000"))
        self.assertEqual(kpis["delivery_rate"], Decimal("100.00"))
        self.assertEqual(kpis["return_rate"], Decimal("0.00"))

    def test_the_store_rows_cover_every_store(self):
        from apps.dashboard.analytics import store_rows

        rows = store_rows()
        slugs = {row["store"].slug for row in rows}
        self.assertIn("boutique-hammamet", slugs)
        self.assertIn(self.flagship.slug, slugs)

        hammamet = next(
            row for row in rows if row["store"].slug == "boutique-hammamet"
        )
        self.assertEqual(hammamet["orders"], 1)
        self.assertEqual(hammamet["gmv"], Decimal("125.000"))
        self.assertEqual(hammamet["gross_margin"], Decimal("25.000"))
        self.assertEqual(hammamet["delivered"], 1)
        self.assertEqual(hammamet["published_products"], 1)

    def test_the_funnel_covers_the_cod_path(self):
        from apps.dashboard.analytics import cod_funnel

        stages = {row["stage"]: row for row in cod_funnel()}
        self.assertIn("Pending", stages)
        self.assertIn("Paid", stages)
        self.assertEqual(stages["Paid"]["count"], 1)
        self.assertEqual(stages["Pending"]["count"], 0)

    def test_the_revenue_series_carries_the_margin(self):
        from apps.dashboard.analytics import revenue_series

        rows = revenue_series()
        self.assertTrue(rows)
        self.assertIn("margin", rows[0])
        self.assertEqual(rows[0]["margin"], Decimal("25.000"))

    def test_the_top_products_are_ranked_by_revenue(self):
        from apps.dashboard.analytics import top_products

        rows = top_products()
        self.assertTrue(rows)
        self.assertEqual(rows[0]["product_title"], "Ventilateur")
        self.assertEqual(rows[0]["revenue"], Decimal("125.000"))

    def test_the_csv_export_is_downloadable(self):
        response = self.client.get(reverse("admin_dashboard:analytics_export"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/csv")
        body = response.content.decode()
        self.assertIn("Boutique Hammamet", body)
        self.assertIn("125.000", body)

    def test_the_analytics_link_is_in_the_superadmin_navigation(self):
        response = self.client.get(reverse("admin_dashboard:overview"))
        self.assertContains(response, reverse("admin_dashboard:analytics"))
