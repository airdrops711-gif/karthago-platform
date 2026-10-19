"""Tests for core views."""
from django.test import TestCase
from django.urls import reverse


class HealthzViewTest(TestCase):
    def test_healthz_endpoint(self):
        response = self.client.get(reverse("healthz"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")
        self.assertTrue(response.json()["database"])
