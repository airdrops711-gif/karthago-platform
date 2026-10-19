"""Order views: 1-step checkout and COD confirmation."""
from django.shortcuts import render, redirect, get_object_or_404
from django.views import View
from django.contrib import messages
from django.http import HttpResponse
from django.db.models import Sum
from .models import Customer, Order, OrderItem, Cart
from apps.catalog.models import Product
from .constants import TUNISIAN_GOVERNORATES


class CheckoutView(View):
    """One-step checkout with COD."""

    def get(self, request):
        return render(request, "storefront/checkout.html", {"governorates": TUNISIAN_GOVERNORATES})

    def post(self, request):
        full_name = request.POST.get("full_name", "").strip()
        phone = request.POST.get("phone", "").strip()
        email = request.POST.get("email", "").strip()
        governorate = request.POST.get("governorate", "")
        delegation = request.POST.get("delegation", "")
        address = request.POST.get("address", "").strip()
        total_amount = request.POST.get("total_amount", 0)

        # Validate phone: exactly 8 digits
        if not phone.isdigit() or len(phone) != 8:
            if request.headers.get("HX-Request"):
                return HttpResponse(
                    '<div class="p-4 rounded-lg bg-red-50 border border-red-200 text-red-800 text-sm">'
                    "Le num&e9ro de t&e9l&e9phone doit contenir exactement 8 chiffres."
                    "</div>",
                    status=400,
                )
            messages.error(request, "Le num&e9ro de t&e9l&e9phone doit contenir exactement 8 chiffres.")
            return redirect("orders:checkout")

        customer = Customer.objects.create(
            full_name=full_name,
            phone=phone,
            email=email,
            governorate=governorate,
            address=f"{delegation}, {address}",
        )
        order = Order.objects.create(
            customer=customer,
            total_amount=total_amount,
            payment_method="COD",
        )

        if request.headers.get("HX-Request"):
            return HttpResponse(
                '<div class="p-6 rounded-lg bg-green-50 border border-green-200">'
                '<div class="flex items-start gap-3">'
                '<div class="bg-green-100 text-green-600 rounded-full p-2">&#10003;</div>'
                '<div>'
                '<h3 class="font-bold text-green-800 text-sm">Commande confirm&eacute;e</h3>'
                '<p class="text-green-700 text-sm mt-1">Votre commande n&deg;{{ order_id }} a &eacute;t&e9; enregistr&e9e.</p>'
                '<p class="text-green-600 text-xs mt-2">Livraison estim&e9e : 24&ndash;48h &agrave; {{ governorate }}.</p>'
                '<p class="text-green-600 text-xs mt-1">Un conseiller vous appellera pour confirmer.</p>'
                '<a href="https://wa.me/216{{ phone }}" class="text-amber-600 text-sm font-medium hover:underline mt-2 block">Contacter le support sur WhatsApp</a>'
                '</div>'
                '</div>'
                '</div>'
                .replace("{{ order_id }}", str(order.id))
                .replace("{{ governorate }}", governorate)
                .replace("{{ phone }}", phone)
            )

        messages.success(request, "Order placed. Awaiting phone confirmation.")
        return redirect("orders:order_detail", order_id=order.id)


class OrderDetailView(View):
    def get(self, request, order_id):
        order = get_object_or_404(Order, pk=order_id)
        return render(request, "storefront/order_detail.html", {"order": order})


class CartView(View):
    """Display cart contents for the current session."""

    def get(self, request):
        session_key = request.session.session_key or request.COOKIES.get("sessionid", "")
        cart_items = Cart.objects.filter(session_key=session_key).select_related("product")
        total = sum(item.product.retail_price * item.quantity for item in cart_items)
        return render(request, "storefront/cart.html", {
            "cart_items": cart_items,
            "total": total,
        })


class AddToCartView(View):
    """Add a product to the cart via HTMX."""

    def post(self, request, product_id):
        product = get_object_or_404(Product, pk=product_id)
        session_key = request.session.session_key or request.COOKIES.get("sessionid", "")
        if not session_key:
            request.session.create()
            session_key = request.session.session_key

        quantity = int(request.POST.get("quantity", 1))
        cart_item, created = Cart.objects.get_or_create(
            session_key=session_key,
            product=product,
            defaults={"quantity": quantity},
        )
        if not created:
            cart_item.quantity += quantity
            cart_item.save()

        cart_count = Cart.objects.filter(session_key=session_key).aggregate(
            total=Sum("quantity")
        )["total"] or 0

        return HttpResponse(
            f'<span class="text-xs text-green-600 font-medium">+{quantity} ajout&eacute;</span>'
            f'<script>document.getElementById("cart-badge").textContent="{cart_count}";</script>'
        )


class RemoveFromCartView(View):
    """Remove an item from the cart."""

    def post(self, request, cart_id):
        session_key = request.session.session_key or request.COOKIES.get("sessionid", "")
        cart_item = get_object_or_404(Cart, pk=cart_id, session_key=session_key)
        cart_item.delete()
        return redirect("orders:cart")
