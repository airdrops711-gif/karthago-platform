"""Tests of the store lifecycle engine and of the COD commission ledger.

Two independent features are covered here:

* the **lifecycle**: suspending a vendor store takes its storefront
  offline, empties its catalogue from the visible pool and evicts its
  documents from the search index; reactivating it restores everything;
* the **commission**: the platform fee is only realized on a delivered
  and paid order — a pending or a returned order carries no commission
  and no payout.

The tests also check the permissions: a non-staff account cannot reach
the superadmin console, and a vendor never sees the ledger of another
vendor.
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.catalog.models import Store, StoreProduct
from apps.catalog.tests.factories import (
    make_flagship,
    make_store,
    make_store_product,
)
from apps.orders.finance import (
    build_settlement,
    platform_financials,
    store_ledger,
)
from apps.orders.models import Customer, Order, OrderItem, PayoutSettlement
from apps.orders.services import change_order_status


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------
class StoreLifecycleTests(TestCase):
    """Suspending and reactivating a vendor store."""

    def setUp(self):
        self.flagship = make_flagship()
        self.store = make_store(name="Boutique Cycle", slug="boutique-cycle")
        self.product = make_store_product(
            self.store, title="Produit de la boutique cycle", featured=True
        )

    def test_a_new_store_is_operational(self):
        self.assertTrue(self.store.is_operational)
        self.assertEqual(self.store.status, Store.STATUS_ACTIVE)

    def test_suspend_takes_the_store_offline(self):
        self.store.suspend("Stock non conforme")

        self.store.refresh_from_db()
        self.assertFalse(self.store.is_operational)
        self.assertFalse(self.store.is_active)
        self.assertEqual(self.store.status, Store.STATUS_SUSPENDED)
        self.assertEqual(self.store.deactivation_reason, "Stock non conforme")
        self.assertIsNotNone(self.store.deactivated_at)

    def test_suspended_store_products_leave_the_visible_pool(self):
        self.assertEqual(StoreProduct.active_objects.count(), 1)

        self.store.suspend()

        self.assertEqual(
            StoreProduct.active_objects.filter(store=self.store).count(), 0
        )
        self.assertEqual(StoreProduct.active_objects.count(), 0)

    def test_suspended_storefront_answers_404(self):
        url = reverse("catalog:substore_home", args=[self.store.slug])
        self.assertEqual(self.client.get(url).status_code, 200)

        self.store.suspend()

        self.assertEqual(self.client.get(url).status_code, 404)

    def test_suspended_store_is_excluded_from_the_flagship_showcase(self):
        """The featured showcase of the homepage must not show a suspended
        store's products."""
        from apps.catalog.tenancy import featured_showcase

        titles = [p.title for p in featured_showcase(limit=12)]
        self.assertIn(self.product.title, titles)

        self.store.suspend()

        titles = [p.title for p in featured_showcase(limit=12)]
        self.assertNotIn(self.product.title, titles)

    def test_reactivate_brings_the_store_back(self):
        self.store.suspend()
        self.store.reactivate()
        self.store.refresh_from_db()

        self.assertTrue(self.store.is_operational)
        self.assertTrue(self.store.is_active)
        self.assertEqual(self.store.status, Store.STATUS_ACTIVE)
        self.assertEqual(self.store.deactivation_reason, "")
        self.assertIsNone(self.store.deactivated_at)
        self.assertEqual(
            StoreProduct.active_objects.filter(store=self.store).count(), 1
        )

        url = reverse("catalog:substore_home", args=[self.store.slug])
        self.assertEqual(self.client.get(url).status_code, 200)

    def test_the_flagship_can_never_be_suspended(self):
        """The flagship owns the root of the site: it stays online."""
        self.flagship.suspend("tentative")
        self.flagship.refresh_from_db()

        self.assertTrue(self.flagship.is_operational)
        self.assertTrue(self.flagship.is_active)
        self.assertEqual(self.flagship.status, Store.STATUS_ACTIVE)

    def test_status_inactive_implies_is_active_false(self):
        """Setting a non-active status flags the store inactive."""
        self.store.status = Store.STATUS_MAINTENANCE
        self.store.save()

        self.store.refresh_from_db()
        self.assertFalse(self.store.is_active)
        self.assertFalse(self.store.is_operational)

    def test_suspension_is_excluded_from_the_search_index_filter(self):
        from apps.catalog.search import operational_store_ids

        ids = operational_store_ids()
        self.assertIn(self.store.pk, ids)

        self.store.suspend()

        self.assertNotIn(self.store.pk, operational_store_ids())


# ---------------------------------------------------------------------------
# Commission
# ---------------------------------------------------------------------------
def make_order(store, *, total="120.000", cost="80.000", status=None, customer=None):
    """Create an order with one line, in the given store."""
    if customer is None:
        customer = Customer.objects.create(
            full_name="Client Test",
            phone="+21620123456",
            governorate="Tunis",
            address="10 rue de la Liberte",
            store=store,
        )
    order = Order.objects.create(
        customer=customer,
        store=store,
        status=status or Order.STATUS_PENDING_CONFIRMATION,
        total_amount=Decimal(total),
        total_cost=Decimal(cost),
        courier_cost=Decimal("7.000"),
    )
    OrderItem.objects.create(
        order=order,
        product_title="Article vendu",
        quantity=1,
        unit_price=Decimal(total),
        unit_cost=Decimal(cost),
    )
    return order


class CommissionCalculationTests(TestCase):
    """The platform fee is only realized on a delivered and paid order."""

    def setUp(self):
        self.flagship = make_flagship()
        self.store = make_store(name="Boutique Finance", slug="boutique-finance")
        self.store.commission_type = Store.COMMISSION_TYPE_PERCENT
        self.store.commission_rate = Decimal("10.00")
        self.store.flat_fee_per_order = Decimal("0.000")
        self.store.save()

    def test_a_pending_order_carries_no_commission(self):
        order = make_order(self.store, status=Order.STATUS_PENDING_CONFIRMATION)
        order.calculate_commissions()
        order.refresh_from_db()

        self.assertEqual(order.platform_cut, Decimal("0.000"))
        self.assertEqual(order.vendor_payout, Decimal("0.000"))

    def test_a_confirmed_order_carries_no_commission(self):
        order = make_order(self.store, status=Order.STATUS_CONFIRMED)
        order.calculate_commissions()
        order.refresh_from_db()

        self.assertEqual(order.platform_cut, Decimal("0.000"))
        self.assertEqual(order.vendor_payout, Decimal("0.000"))

    def test_a_delivered_order_realizes_the_percentage(self):
        order = make_order(self.store, total="120.000", cost="80.000")
        change_order_status(order, Order.STATUS_DELIVERED_AND_PAID)
        order.refresh_from_db()

        # 10% of 120.000 = 12.000
        self.assertEqual(order.platform_cut, Decimal("12.000"))
        # 120.000 - 80.000 - 7.000 - 12.000 = 21.000
        self.assertEqual(order.vendor_payout, Decimal("21.000"))

    def test_a_returned_order_carries_no_commission(self):
        order = make_order(self.store, status=Order.STATUS_SHIPPED)
        change_order_status(order, Order.STATUS_DELIVERED_AND_PAID)
        order.refresh_from_db()
        self.assertGreater(order.platform_cut, Decimal("0.000"))

        change_order_status(order, Order.STATUS_RETURNED)
        order.refresh_from_db()

        self.assertEqual(order.platform_cut, Decimal("0.000"))
        self.assertEqual(order.vendor_payout, Decimal("0.000"))

    def test_the_percentage_keeps_the_millime_precision(self):
        """A gross total that is not a round number keeps three decimals."""
        order = make_order(self.store, total="99.999", cost="60.000")
        change_order_status(order, Order.STATUS_DELIVERED_AND_PAID)
        order.refresh_from_db()

        # 10% of 99.999 = 9.9999 -> 10.000
        self.assertEqual(order.platform_cut, Decimal("10.000"))
        self.assertEqual(order.platform_cut.as_tuple().exponent, -3)

    def test_the_flat_fee_commission(self):
        self.store.commission_type = Store.COMMISSION_TYPE_FLAT
        self.store.flat_fee_per_order = Decimal("5.500")
        self.store.save()

        order = make_order(self.store, total="120.000", cost="80.000")
        change_order_status(order, Order.STATUS_DELIVERED_AND_PAID)
        order.refresh_from_db()

        self.assertEqual(order.platform_cut, Decimal("5.500"))
        # 120.000 - 80.000 - 7.000 - 5.500 = 27.500
        self.assertEqual(order.vendor_payout, Decimal("27.500"))

    def test_the_hybrid_commission(self):
        self.store.commission_type = Store.COMMISSION_TYPE_HYBRID
        self.store.commission_rate = Decimal("10.00")
        self.store.flat_fee_per_order = Decimal("2.000")
        self.store.save()

        order = make_order(self.store, total="120.000", cost="80.000")
        change_order_status(order, Order.STATUS_DELIVERED_AND_PAID)
        order.refresh_from_db()

        # 10% of 120.000 + 2.000 = 14.000
        self.assertEqual(order.platform_cut, Decimal("14.000"))

    def test_the_vendor_payout_never_goes_negative(self):
        """A loss stays a loss: it is not turned into a debt."""
        order = make_order(self.store, total="50.000", cost="80.000")
        change_order_status(order, Order.STATUS_DELIVERED_AND_PAID)
        order.refresh_from_db()

        self.assertGreater(order.platform_cut, Decimal("0.000"))
        self.assertEqual(order.vendor_payout, Decimal("0.000"))

    def test_the_commission_uses_the_rule_of_the_store(self):
        """Two stores, two rules, two cuts on the same gross total."""
        other = make_store(name="Boutique Other", slug="boutique-other")
        other.commission_type = Store.COMMISSION_TYPE_PERCENT
        other.commission_rate = Decimal("20.00")
        other.save()

        order_a = make_order(self.store, total="120.000", cost="80.000")
        order_b = make_order(other, total="120.000", cost="80.000")
        change_order_status(order_a, Order.STATUS_DELIVERED_AND_PAID)
        change_order_status(order_b, Order.STATUS_DELIVERED_AND_PAID)

        order_a.refresh_from_db()
        order_b.refresh_from_db()
        self.assertEqual(order_a.platform_cut, Decimal("12.000"))
        self.assertEqual(order_b.platform_cut, Decimal("24.000"))

    def test_an_order_without_store_carries_no_commission(self):
        order = make_order(self.flagship, total="120.000", cost="80.000")
        order.store = None
        order.save()
        order.calculate_commissions()
        order.refresh_from_db()

        self.assertEqual(order.platform_cut, Decimal("0.000"))
        self.assertEqual(order.vendor_payout, Decimal("0.000"))


class LedgerTests(TestCase):
    """The financial aggregation and the payout batches."""

    def setUp(self):
        self.flagship = make_flagship()
        self.store = make_store(name="Boutique Ledger", slug="boutique-ledger")
        self.store.commission_type = Store.COMMISSION_TYPE_PERCENT
        self.store.commission_rate = Decimal("10.00")
        self.store.save()

    def test_the_ledger_only_counts_the_delivered_orders(self):
        make_order(self.store, total="120.000", status=Order.STATUS_CONFIRMED)
        delivered = make_order(self.store, total="200.000")
        change_order_status(delivered, Order.STATUS_DELIVERED_AND_PAID)

        financials = platform_financials(self.store)

        self.assertEqual(financials["delivered_orders"], 1)
        self.assertEqual(financials["gmv"], Decimal("200.000"))
        self.assertEqual(financials["platform_cut"], Decimal("20.000"))
        self.assertEqual(financials["average_commission"], Decimal("20.000"))

    def test_the_store_ledger_exposes_the_totals(self):
        delivered = make_order(self.store, total="200.000", cost="120.000")
        change_order_status(delivered, Order.STATUS_DELIVERED_AND_PAID)

        ledger = store_ledger(self.store)

        self.assertEqual(ledger["total_orders"], 1)
        self.assertEqual(ledger["total_gmv"], Decimal("200.000"))
        self.assertEqual(ledger["platform_cut"], Decimal("20.000"))
        # 200.000 - 120.000 - 7.000 - 20.000 = 53.000
        self.assertEqual(ledger["vendor_payout"], Decimal("53.000"))
        self.assertTrue(ledger["by_status"])
        self.assertIn("settlements", ledger)

    def test_the_unsettled_balance_is_reported(self):
        delivered = make_order(self.store, total="200.000")
        change_order_status(delivered, Order.STATUS_DELIVERED_AND_PAID)

        financials = platform_financials(self.store)
        self.assertEqual(financials["unsettled_orders"], 1)
        self.assertEqual(financials["unsettled_vendor_payout"], financials["vendor_payout"])

    def test_a_settlement_batches_the_delivered_orders(self):
        delivered = make_order(self.store, total="200.000", cost="120.000")
        change_order_status(delivered, Order.STATUS_DELIVERED_AND_PAID)

        settlement = build_settlement(self.store)

        self.assertIsNotNone(settlement)
        self.assertEqual(settlement.total_delivered_orders, 1)
        self.assertEqual(settlement.total_gmv, Decimal("200.000"))
        self.assertEqual(settlement.total_platform_cut, Decimal("20.000"))
        self.assertEqual(settlement.net_payout_to_vendor, Decimal("53.000"))
        self.assertTrue(settlement.reference.startswith("PAY-"))

        delivered.refresh_from_db()
        self.assertEqual(delivered.settlement_batch, settlement)
        self.assertFalse(delivered.is_settled)

    def test_a_settlement_without_delivered_orders_is_none(self):
        make_order(self.store, total="200.000", status=Order.STATUS_CONFIRMED)
        self.assertIsNone(build_settlement(self.store))

    def test_a_settlement_never_pays_twice(self):
        delivered = make_order(self.store, total="200.000")
        change_order_status(delivered, Order.STATUS_DELIVERED_AND_PAID)

        first = build_settlement(self.store)
        self.assertIsNotNone(first)
        # A second batch finds nothing left to pay.
        self.assertIsNone(build_settlement(self.store))

    def test_marking_a_settlement_paid_settles_its_orders(self):
        delivered = make_order(self.store, total="200.000")
        change_order_status(delivered, Order.STATUS_DELIVERED_AND_PAID)

        settlement = build_settlement(self.store)
        settlement.mark_paid()
        settlement.refresh_from_db()

        self.assertTrue(settlement.is_paid)
        self.assertIsNotNone(settlement.paid_at)

        delivered.refresh_from_db()
        self.assertTrue(delivered.is_settled)

        financials = platform_financials(self.store)
        self.assertEqual(financials["unsettled_orders"], 0)


# ---------------------------------------------------------------------------
# The frontend and the permissions
# ---------------------------------------------------------------------------
class FinanceConsoleTests(TestCase):
    """The superadmin financial console and the vendor finance page."""

    def setUp(self):
        user_model = get_user_model()
        self.staff = user_model.objects.create_user(
            username="superadmin", password="secret-pass-123", is_staff=True
        )
        self.vendor = user_model.objects.create_user(
            username="vendeur", password="secret-pass-123", is_staff=True
        )
        self.other_vendor = user_model.objects.create_user(
            username="vendeur2", password="secret-pass-123", is_staff=True
        )
        self.plain = user_model.objects.create_user(
            username="client", password="secret-pass-123"
        )
        self.flagship = make_flagship()
        self.store = make_store(
            name="Boutique Console", slug="boutique-console", owner=self.vendor
        )
        self.other_store = make_store(
            name="Boutique Autres", slug="boutique-autres", owner=self.other_vendor
        )

    def test_the_financial_console_renders_for_a_staff_account(self):
        self.client.force_login(self.staff)
        response = self.client.get(reverse("admin_dashboard:financials"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ledger financier")

    def test_the_financial_console_is_closed_to_a_plain_account(self):
        self.client.force_login(self.plain)
        response = self.client.get(reverse("admin_dashboard:financials"))
        self.assertEqual(response.status_code, 302)

    def test_the_csv_export_is_available_to_a_staff_account(self):
        self.client.force_login(self.staff)
        response = self.client.get(reverse("admin_dashboard:financials_export"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/csv; charset=utf-8")

    def test_the_vendor_finances_page_renders(self):
        self.client.force_login(self.vendor)
        response = self.client.get(reverse("dashboard:finances"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Mes finances")

    def test_the_vendor_finances_page_is_closed_to_anonymous(self):
        response = self.client.get(reverse("dashboard:finances"))
        self.assertEqual(response.status_code, 302)

    def test_a_suspended_vendor_sees_the_suspension_banner(self):
        self.store.suspend("Non conformite")
        self.client.force_login(self.vendor)
        response = self.client.get(reverse("dashboard:finances"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "suspendue")

    def test_a_vendor_only_sees_its_own_ledger(self):
        """The finances page of a vendor shows its own numbers only."""
        delivered = make_order(self.store, total="200.000")
        change_order_status(delivered, Order.STATUS_DELIVERED_AND_PAID)
        other = make_order(self.other_store, total="900.000")
        change_order_status(other, Order.STATUS_DELIVERED_AND_PAID)

        self.client.force_login(self.vendor)
        response = self.client.get(reverse("dashboard:finances"))

        ledger = response.context["ledger"]
        self.assertEqual(ledger["gmv"], Decimal("200.000"))
        self.assertEqual(ledger["total_orders"], 1)
        # The other store's gross total must not leak into the page.
        self.assertNotContains(response, "900.000")

    def test_the_superadmin_can_suspend_a_store(self):
        self.client.force_login(self.staff)
        response = self.client.post(
            reverse("admin_dashboard:store_toggle_status", args=[self.store.pk]),
            {"action": "suspend", "deactivation_reason": "Test"},
            follow=True,
        )
        self.assertEqual(response.status_code, 200)

        self.store.refresh_from_db()
        self.assertEqual(self.store.status, Store.STATUS_SUSPENDED)
        self.assertEqual(self.store.deactivation_reason, "Test")

    def test_the_htmx_suspension_answers_the_new_card(self):
        """The HTMX button swaps the card: the server returns the card
        in its new state, not a redirect."""
        self.client.force_login(self.staff)
        response = self.client.post(
            reverse("admin_dashboard:store_toggle_status", args=[self.store.pk]),
            {"action": "suspend", "deactivation_reason": "Rupture"},
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Rupture")
        self.assertContains(response, "R&eacute;activer la boutique")

        self.store.refresh_from_db()
        self.assertEqual(self.store.status, Store.STATUS_SUSPENDED)

    def test_the_htmx_suspension_carries_the_csrf_token(self):
        """A button without a form must not post without a token: the
        card carries one, otherwise Django rejects the request."""
        self.client.force_login(self.staff)
        response = self.client.get(reverse("admin_dashboard:stores"))
        self.assertContains(response, "csrfmiddlewaretoken")

    def test_the_commission_page_renders(self):
        self.client.force_login(self.staff)
        response = self.client.get(
            reverse("admin_dashboard:store_commission", args=[self.store.pk])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Commission de")

    def test_the_flagship_cannot_be_suspended(self):
        self.client.force_login(self.staff)
        response = self.client.post(
            reverse("admin_dashboard:store_toggle_status", args=[self.flagship.pk]),
            {"action": "suspend"},
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.flagship.refresh_from_db()
        self.assertTrue(self.flagship.is_operational)

    def test_a_plain_account_cannot_suspend_a_store(self):
        self.client.force_login(self.plain)
        self.client.post(
            reverse("admin_dashboard:store_toggle_status", args=[self.store.pk]),
            {"action": "suspend"},
        )
        self.store.refresh_from_db()
        self.assertEqual(self.store.status, Store.STATUS_ACTIVE)

    def test_the_superadmin_can_update_the_commission_rule(self):
        self.client.force_login(self.staff)
        response = self.client.post(
            reverse("admin_dashboard:store_commission", args=[self.store.pk]),
            {
                "commission_type": Store.COMMISSION_TYPE_HYBRID,
                "commission_rate": "12.5",
                "flat_fee_per_order": "3.250",
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)

        self.store.refresh_from_db()
        self.assertEqual(self.store.commission_type, Store.COMMISSION_TYPE_HYBRID)
        self.assertEqual(self.store.commission_rate, Decimal("12.50"))
        self.assertEqual(self.store.flat_fee_per_order, Decimal("3.250"))

    def test_the_stores_console_lists_the_lifecycle_state(self):
        self.store.suspend("Rupture de stock")
        self.client.force_login(self.staff)
        response = self.client.get(reverse("admin_dashboard:stores"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Rupture de stock")


class SettlementModelTests(TestCase):
    """The payout batch model itself."""

    def test_the_reference_is_unique(self):
        store = make_store(name="Boutique Ref", slug="boutique-ref")
        PayoutSettlement.objects.create(store=store, reference="PAY-20260101-REF")
        with self.assertRaises(Exception):
            PayoutSettlement.objects.create(store=store, reference="PAY-20260101-REF")
