"""Tests for the bilingual layer (French / Tunisian Arabic).

The platform speaks two languages. This test file covers:

1. the language switcher (``/i18n/setlang/``) and its cookie,
2. the rendering of the pages in Arabic (and the RTL direction),
3. the number formats, which must stay identical in both languages
   (the prices are stored in millimes: ``100.000`` DT),
4. the fact that the ``.mo`` catalogues are compiled and installed.
"""
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import translation
from django.utils.formats import localize

from apps.catalog.tests.factories import make_flagship, make_store_product


class LanguageSwitcherTest(TestCase):
    """The switcher stores the language in a cookie and redirects back."""

    def setUp(self):
        self.flagship = make_flagship()
        self.product = make_store_product(
            self.flagship, title="Television", cost="100.000", category="TV"
        )

    def test_the_switcher_is_present_on_the_storefront(self):
        response = self.client.get(reverse("catalog:product_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("set_language"))
        self.assertContains(response, "FR")

    def test_posting_arabic_sets_the_cookie_and_redirects_back(self):
        response = self.client.post(
            reverse("set_language"),
            {"language": "ar", "next": "/catalogue/"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "/catalogue/")
        self.assertEqual(response.cookies["karthago_language"].value, "ar")

    def test_the_language_cookie_switches_the_rendered_page(self):
        self.client.post(
            reverse("set_language"), {"language": "ar", "next": "/catalogue/"}
        )
        response = self.client.get("/catalogue/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["LANGUAGE_CODE"], "ar")
        self.assertTrue(response.context["is_rtl"])
        self.assertContains(response, 'dir="rtl"')

    def test_the_page_falls_back_to_french(self):
        response = self.client.get("/catalogue/")
        self.assertEqual(response.context["LANGUAGE_CODE"], "fr")
        self.assertFalse(response.context["is_rtl"])

    def test_an_unknown_language_falls_back_to_the_default(self):
        response = self.client.post(
            reverse("set_language"), {"language": "de", "next": "/catalogue/"}
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.cookies["karthago_language"].value, "fr")

    def test_an_external_next_url_is_not_followed(self):
        """The switcher must not become an open redirect."""
        response = self.client.post(
            reverse("set_language"),
            {"language": "ar", "next": "https://evil.example.com/"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "/")

    def test_the_switcher_works_from_a_get_request(self):
        response = self.client.get(
            reverse("set_language"), {"language": "ar", "next": "/catalogue/"}
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.cookies["karthago_language"].value, "ar")


class NumberFormatTest(TestCase):
    """The prices must look the same in French and in Arabic.

    The prices are stored in millimes: ``Decimal("100.000")`` is
    100 dinars 000 millimes. Django's own ``fr`` locale would render it
    ``100,000`` (comma as the decimal separator) and its ``ar`` locale
    ``100.000`` (dot as the thousands separator). The project ships its
    own format modules to keep the historical rendering.
    """

    def test_the_decimals_keep_their_dot_in_french(self):
        with translation.override("fr"):
            self.assertEqual(localize(Decimal("100.000")), "100.000")
            self.assertEqual(localize(Decimal("880.000")), "880.000")

    def test_the_decimals_keep_their_dot_in_arabic(self):
        with translation.override("ar"):
            self.assertEqual(localize(Decimal("100.000")), "100.000")
            self.assertEqual(localize(Decimal("880.000")), "880.000")

    def test_the_thousands_are_grouped_with_a_comma(self):
        with translation.override("fr"):
            self.assertEqual(localize(Decimal("1234567.500")), "1,234,567.500")
        with translation.override("ar"):
            self.assertEqual(localize(Decimal("1234567.500")), "1,234,567.500")

    def test_the_cart_page_shows_the_price_with_a_dot(self):
        self.flagship = make_flagship()
        self.product = make_store_product(
            self.flagship, title="Ordinateur", cost="100.000", category="Informatique"
        )
        response = self.client.post(
            reverse("orders:add_to_cart", args=[self.product.id]),
            {"quantity": 2},
        )
        self.assertIn(response.status_code, (200, 302))
        response = self.client.get(reverse("orders:cart"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "220.000")


class ArabicCatalogueTest(TestCase):
    """The Arabic catalogue must be compiled and installed."""

    def test_the_arabic_catalogue_is_installed(self):
        with translation.override("ar"):
            self.assertEqual(translation.gettext("Catalogue"), "الكتالوج")

    def test_the_arabic_plural_forms_are_installed(self):
        """Arabic has six plural forms; they must all be installed."""
        with translation.override("ar"):
            one = translation.ngettext(
                "%(counter)s produit", "%(counter)s produits", 1
            )
            many = translation.ngettext(
                "%(counter)s produit", "%(counter)s produits", 5
            )
        self.assertIn("منتج", one)
        self.assertIn("منتجات", many)
        self.assertNotEqual(one, many)

    def test_a_french_phrase_is_translated_into_arabic(self):
        with translation.override("ar"):
            translated = translation.gettext("Panier")
        self.assertNotEqual(translated, "Panier")
