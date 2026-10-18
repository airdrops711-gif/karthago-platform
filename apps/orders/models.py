"""Order models for Karthago Platform (Tunisian COD flow)."""
from django.db import models
from django.core.validators import MinValueValidator
from .constants import TUNISIAN_GOVERNORATES


class Customer(models.Model):
    full_name = models.CharField(max_length=200)
    phone = models.CharField(max_length=20, help_text="Tunisian phone number.")
    email = models.EmailField(blank=True)
    governorate = models.CharField(max_length=50, choices=TUNISIAN_GOVERNORATES)
    address = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.full_name


class Order(models.Model):
    STATUS_PENDING_CONFIRMATION = "PENDING_CONFIRMATION"
    STATUS_CONFIRMED = "CONFIRMED"
    STATUS_ORDERED_FROM_SUPPLIER = "ORDERED_FROM_SUPPLIER"
    STATUS_SHIPPED = "SHIPPED"
    STATUS_DELIVERED_AND_PAID = "DELIVERED_AND_PAID"
    STATUS_RETURNED = "RETURNED"

    STATUS_CHOICES = [
        (STATUS_PENDING_CONFIRMATION, "Pending Confirmation"),
        (STATUS_CONFIRMED, "Confirmed"),
        (STATUS_ORDERED_FROM_SUPPLIER, "Ordered From Supplier"),
        (STATUS_SHIPPED, "Shipped"),
        (STATUS_DELIVERED_AND_PAID, "Delivered & Paid"),
        (STATUS_RETURNED, "Returned (Retour)"),
    ]

    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name="orders")
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default=STATUS_PENDING_CONFIRMATION)
    total_amount = models.DecimalField(max_digits=10, decimal_places=3, validators=[MinValueValidator(0)])
    payment_method = models.CharField(max_length=20, default="COD")
    confirmed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Order {self.id} - {self.customer.full_name}"


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    product_title = models.CharField(max_length=255)
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=10, decimal_places=3, validators=[MinValueValidator(0)])

    def line_total(self):
        return self.unit_price * self.quantity

    def __str__(self):
        return f"{self.quantity}x {self.product_title}"


class Delivery(models.Model):
    order = models.OneToOneField(Order, on_delete=models.CASCADE, related_name="delivery")
    tracking_number = models.CharField(max_length=100, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    paid_on_delivery = models.BooleanField(default=False)
    returned_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Delivery for Order {self.order.id}"
