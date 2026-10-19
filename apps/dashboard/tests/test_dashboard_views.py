"""Tests for dashboard views."""
from django.test import TestCase
from django.urls import reverse
from django.contrib.auth.models import User


class DashboardOverviewTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(
            username="admin", email="admin@example.com", password="admin123"
        )
        self.client.login(username="admin", password="admin123")

    def test_dashboard_overview_requires_login(self):
        self.client.logout()
        response = self.client.get(reverse("dashboard:overview"))
        self.assertEqual(response.status_code, 302)  # Redirect to login

    def test_dashboard_overview_authenticated(self):
        response = self.client.get(reverse("dashboard:overview"))
        self.assertEqual(response.status_code, 200)
