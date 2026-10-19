"""Order services: build an order from the cart, server-side.

The checkout used to trust the `total_amount` posted by the browser. That
is a pricing hole: a customer could post any amount and order a 400 DT
television for 1 DT. Here the order is always priced from the cart rows
in the database.
"""
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.catalog.models import Product
from .models import Cart, Customer, Order, OrderEvent, OrderItem


def cart_lines(session_key):
    """Cart rows with their product, ready to be priced."""
    if not session_key:
        return Cart.objects.none()
    return (
        Cart.objects.filter(session_key=session_key)
        .select_related("product", "product__supplier", "product__category")
        .order_by("created_at")
    )


def cart_total(session_key):
    """Total retail price of the cart, in TND."""
    total = Decimal("0.000")
    for item in cart_lines(session_key):
        total += item.product.retail_price * item.quantity
    return total.quantize(Decimal("0.001"))


def _first_image(product):
    images = product.images.all()
    if not images:
        return ""
    return images[0].image or ""


def build_order_items(cart_queryset):
    """Turn cart rows into unsaved OrderItem rows.

    The supplier name, the original cost and the source URL are copied from
    the product: a later re-scrape may change them, but the order must keep
    the values that were actually charged.
    """
    items = []
    for cart_row in cart_queryset:
        product = cart_row.product
        if not product.is_active:
            # The product was deactivated between the add-to-cart and the
            # checkout: it cannot be ordered.
            continue
        items.append(
            OrderItem(
                product=product,
                product_title=product.title[:255],
                quantity=cart_row.quantity,
                unit_price=product.retail_price,
                unit_cost=product.raw_cost,
                currency=product.currency or "TND",
                currency_rate=product.currency_rate or Decimal("1"),
                supplier_name=(product.supplier.name if product.supplier else "")[:100],
                source_url=(product.source or "")[:500],
                image_url=_first_image(product)[:500],
                compare_at_price=product.compare_at_price or Decimal("0.000"),
            )
        )
    return items


@transaction.atomic
def create_order_from_cart(
    session_key,
    *,
    full_name,
    phone,
    email="",
    governorate="",
    delegation="",
    address="",
    notes="",
):
    """Create an order from the customer's cart.

    Returns ``(order, items)``. The cart is emptied on success, and the
    order is priced entirely from the database.
    """
    rows = list(cart_lines(session_key))
    items = build_order_items(rows)
    if not items:
        raise ValueError("Panier vide ou produits indisponibles.")

    customer = Customer.objects.create(
        full_name=full_name[:200],
        phone=phone[:20],
        email=email[:254],
        governorate=governorate[:50],
        address=f"{delegation}, {address}".strip(", ")[:2000],
    )

    total_amount = sum((item.unit_price * item.quantity for item in items), Decimal("0.000"))
    total_cost = sum((item.line_cost_tnd() for item in items), Decimal("0.000"))

    order = Order.objects.create(
        customer=customer,
        total_amount=total_amount.quantize(Decimal("0.001")),
        total_cost=total_cost.quantize(Decimal("0.001")),
        payment_method="COD",
        notes=notes[:2000],
    )
    for item in items:
        item.order = order
        item.save()

    OrderEvent.objects.create(
        order=order,
        from_status="",
        to_status=Order.STATUS_PENDING_CONFIRMATION,
        note="Commande reçue depuis la boutique.",
        created_by="storefront",
    )

    # The cart is emptied only once the order exists, so a failure never
    # loses the customer's selection.
    Cart.objects.filter(session_key=session_key).delete()

    return order, items


@transaction.atomic
def change_order_status(order, new_status, *, note="", user=None):
    """Move an order to a new status and record the event.

    Returns the created OrderEvent. The confirmation timestamp is set the
    first time the order leaves the pending state.
    """
    from .models import Order as OrderModel

    valid = {choice for choice, _ in OrderModel.STATUS_CHOICES}
    if new_status not in valid:
        raise ValueError(f"Statut inconnu: {new_status}")

    previous = order.status
    order.status = new_status
    if new_status != OrderModel.STATUS_PENDING_CONFIRMATION and not order.confirmed_at:
        order.confirmed_at = timezone.now()
    order.save(update_fields=["status", "confirmed_at", "updated_at"])

    event = OrderEvent.objects.create(
        order=order,
        from_status=previous,
        to_status=new_status,
        note=note,
        created_by=(user.get_username() if user is not None else ""),
    )
    return event


def order_summary(order):
    """Everything the dashboard needs about one order, in one dict."""
    items = list(order.items.all())
    return {
        "order": order,
        "items": items,
        "item_count": sum(item.quantity for item in items),
        "total": order.total_amount,
        "cost": order.total_cost,
        "margin": order.total_amount - order.total_cost,
        "margin_percent": order.margin_percent,
        "suppliers": sorted({item.supplier_name for item in items if item.supplier_name}),
    }
