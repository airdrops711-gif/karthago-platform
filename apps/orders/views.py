"""Order views: 1-step checkout and COD confirmation."""
from django.shortcuts import render, redirect, get_object_or_404
from django.views import View
from django.contrib import messages
from .models import Customer, Order, OrderItem
from .constants import TUNISIAN_GOVERNORATES


class CheckoutView(View):
    """One-step checkout with COD."""

    def get(self, request):
        return render(request, "storefront/checkout.html", {"governorates": TUNISIAN_GOVERNORATES})

    def post(self, request):
        customer = Customer.objects.create(
            full_name=request.POST.get("full_name", ""),
            phone=request.POST.get("phone", ""),
            email=request.POST.get("email", ""),
            governorate=request.POST.get("governorate", ""),
            address=request.POST.get("address", ""),
        )
        order = Order.objects.create(
            customer=customer,
            total_amount=request.POST.get("total_amount", 0),
            payment_method="COD",
        )
        # In a real flow, cart items would be converted here.
        messages.success(request, "Order placed. Awaiting phone confirmation.")
        return redirect("orders:order_detail", order_id=order.id)


class OrderDetailView(View):
    def get(self, request, order_id):
        order = get_object_or_404(Order, pk=order_id)
        return render(request, "storefront/order_detail.html", {"order": order})
