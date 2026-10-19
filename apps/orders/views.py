"""Order views: 1-step checkout and COD confirmation."""
from django.shortcuts import render, redirect, get_object_or_404
from django.views import View
from django.contrib import messages
from django.http import HttpResponse
from django.db.models import Sum

from .models import Customer, Order, OrderItem, Cart
from apps.catalog.models import Product
from .services import (
    cart_lines,
    cart_total,
    create_order_from_cart,
    change_order_status,
)
from .constants import TUNISIAN_GOVERNORATES

# The checkout modal is opened by this event (see static/js/app.js).
OPEN_CHECKOUT_EVENT = "karthago:open-checkout"


def _session_key(request):
    """The cart session key, creating the session when needed."""
    key = request.session.session_key or request.COOKIES.get("sessionid", "")
    if not key:
        request.session.create()
        key = request.session.session_key
    return key


class CheckoutView(View):
    """One-step checkout with COD, priced from the server-side cart."""

    def get(self, request):
        session_key = _session_key(request)
        items = list(cart_lines(session_key))
        return render(
            request,
            "storefront/checkout.html",
            {
                "governorates": TUNISIAN_GOVERNORATES,
                "cart_items": items,
                "total": cart_total(session_key),
            },
        )

    def post(self, request):
        full_name = request.POST.get("full_name", "").strip()
        phone = request.POST.get("phone", "").strip()
        email = request.POST.get("email", "").strip()
        governorate = request.POST.get("governorate", "")
        delegation = request.POST.get("delegation", "").strip()
        address = request.POST.get("address", "").strip()
        notes = request.POST.get("notes", "").strip()

        error = None
        if not full_name:
            error = "Le nom complet est obligatoire."
        elif not phone.isdigit() or len(phone) != 8:
            error = "Le numéro de téléphone doit contenir exactement 8 chiffres."
        elif not address:
            error = "L'adresse est obligatoire."

        session_key = _session_key(request)

        if error is None:
            try:
                order, items = create_order_from_cart(
                    session_key,
                    full_name=full_name,
                    phone=phone,
                    email=email,
                    governorate=governorate,
                    delegation=delegation,
                    address=address,
                    notes=notes,
                )
            except ValueError:
                error = "Votre panier est vide."

        if error:
            if request.headers.get("HX-Request"):
                return HttpResponse(
                    '<div class="p-4 rounded-lg bg-red-50 border border-red-200 text-red-800 text-sm">'
                    f"{error}"
                    "</div>",
                    status=400,
                )
            messages.error(request, error)
            return redirect("orders:checkout")

        if request.headers.get("HX-Request"):
            return HttpResponse(
                '<div class="p-6 rounded-lg bg-green-50 border border-green-200">'
                '<div class="flex items-start gap-3">'
                '<div class="bg-green-100 text-green-600 rounded-full p-2">&#10003;</div>'
                '<div>'
                '<h3 class="font-bold text-green-800 text-sm">Commande confirm&eacute;e</h3>'
                f'<p class="text-green-700 text-sm mt-1">Votre commande n&deg;{order.id} a &eacute;t&eacute; enregistr&eacute;e.</p>'
                f'<p class="text-green-600 text-xs mt-2">Livraison estim&eacute;e : 24&ndash;48h &agrave; {governorate}.</p>'
                '<p class="text-green-600 text-xs mt-1">Un conseiller vous appellera pour confirmer.</p>'
                f'<a href="https://wa.me/216{phone}" class="text-amber-600 text-sm font-medium hover:underline mt-2 block">Contacter le support sur WhatsApp</a>'
                '</div>'
                '</div>'
                '</div>'
            )

        messages.success(request, "Commande enregistrée. En attente de confirmation téléphonique.")
        return redirect("orders:order_detail", order_id=order.id)


class OrderDetailView(View):
    """Public order tracking page (read-only, no customer data leak)."""

    def get(self, request, order_id):
        order = get_object_or_404(
            Order.objects.select_related("customer").prefetch_related("items", "events"),
            pk=order_id,
        )
        return render(request, "storefront/order_detail.html", {"order": order})


class CartView(View):
    """Display cart contents for the current session."""

    def get(self, request):
        session_key = _session_key(request)
        items = list(cart_lines(session_key))
        return render(
            request,
            "storefront/cart.html",
            {
                "cart_items": items,
                "total": cart_total(session_key),
            },
        )


class AddToCartView(View):
    """Add a product to the cart via HTMX."""

    def post(self, request, product_id):
        product = get_object_or_404(Product, pk=product_id)
        session_key = _session_key(request)

        quantity = int(request.POST.get("quantity", 1) or 1)
        quantity = max(1, quantity)
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

        # The cart badge exists in two places (desktop navbar, mobile
        # navbar). Both are updated so the count never goes stale.
        return HttpResponse(
            f'<span class="text-xs text-green-600 font-medium">+{quantity} ajout&eacute;</span>'
            f'<script>'
            f'document.querySelectorAll("[data-cart-badge]").forEach(function (el) {{ el.textContent = "{cart_count}"; }});'
            f'</script>'
        )


class UpdateCartQuantityView(View):
    """Change the quantity of a cart line via HTMX."""

    def post(self, request, cart_id):
        session_key = _session_key(request)
        cart_item = get_object_or_404(Cart, pk=cart_id, session_key=session_key)
        quantity = int(request.POST.get("quantity", 1) or 1)
        if quantity <= 0:
            cart_item.delete()
        else:
            cart_item.quantity = quantity
            cart_item.save()

        total = cart_total(session_key)
        cart_count = Cart.objects.filter(session_key=session_key).aggregate(
            total=Sum("quantity")
        )["total"] or 0
        return HttpResponse(
            f'<span class="text-xs text-green-600 font-medium">Mis &agrave; jour</span>'
            f'<script>'
            f'document.querySelectorAll("[data-cart-badge]").forEach(function (el) {{ el.textContent = "{cart_count}"; }});'
            f'var t = document.getElementById("cart-total"); if (t) {{ t.textContent = "{total} DT"; }}'
            f'</script>'
        )


class RemoveFromCartView(View):
    """Remove an item from the cart."""

    def post(self, request, cart_id):
        session_key = _session_key(request)
        cart_item = get_object_or_404(Cart, pk=cart_id, session_key=session_key)
        cart_item.delete()
        return redirect("orders:cart")
