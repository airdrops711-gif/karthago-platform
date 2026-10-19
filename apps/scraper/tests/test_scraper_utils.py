"""Tests for scraper utilities."""
from decimal import Decimal
from django.test import TestCase
from apps.scraper.utils import normalize_tunisian_price


class NormalizeTunisianPriceTest(TestCase):
    def test_price_with_dt(self):
        result = normalize_tunisian_price("149,000 DT")
        self.assertEqual(result, Decimal("149.000"))

    def test_price_with_tnd(self):
        result = normalize_tunisian_price("149.000 TND")
        self.assertEqual(result, Decimal("149.000"))

    def test_price_with_arabic_dt(self):
        result = normalize_tunisian_price("149,000 د.ت")
        self.assertEqual(result, Decimal("149.000"))

    def test_price_without_currency(self):
        result = normalize_tunisian_price("149,000")
        self.assertEqual(result, Decimal("149.000"))

    def test_price_none(self):
        result = normalize_tunisian_price(None)
        self.assertEqual(result, Decimal("0.000"))

    def test_price_empty(self):
        result = normalize_tunisian_price("")
        self.assertEqual(result, Decimal("0.000"))

    def test_price_simple(self):
        result = normalize_tunisian_price("149 DT")
        self.assertEqual(result, Decimal("149.000"))

    def test_price_three_decimals(self):
        result = normalize_tunisian_price("149,500 DT")
        self.assertEqual(result, Decimal("149.500"))
