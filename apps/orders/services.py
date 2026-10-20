"""Cart services: a session cart scoped to one tenant.

The cart holds ``StoreProduct`` rows — the tenant catalogue — so a
visitor on a vendor sub-store never adds a flagship product, and the
price charged is always the one of the store that sells it.
"""
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.catalog.models import Store, StoreProduct
from .models import Cart, Customer, Order, OrderEvent, OrderItem


def _first_image(store_product):
    """The first image of a tenant product."""
    if store_product.image_url:
        return store_product.image_url
    for url in store_product.image_urls or []:
        if url:
            return url
    return ""


def cart_store(session_key):
    """The store the cart of this session belongs to.

    The cart rows carry the store, so the store is read back from the
    first row. An empty cart has no store yet: the flagship is used.
    """
    from apps.catalog.tenancy import flagship_store

    row = Cart.objects.filter(session_key=session_key).exclude(store__isnull=True).first()
    if row is not None:
        return row.store
    return flagship_store()


def cart_lines(session_key, store=None):
    """Cart rows with their product, ready to be priced."""
    if not session_key:
        return Cart.objects.none()
    queryset = Cart.objects.filter(session_key=session_key)
    if store is not None:
        queryset = queryset.filter(store=store)
    return queryset.select_related(
        "product", "store"
    ).order_by("created_at")


def cart_total(session_key, store=None):
    """Total retail price of the cart, in TND."""
    total = Decimal("0.000")
    for item in cart_lines(session_key, store):
        total += item.product.selling_price * item.quantity
    return total.quantize(Decimal("0.001"))


def build_order_items(cart_queryset):
    """Turn cart rows into unsaved OrderItem rows.

    The supplier name, the original cost and the source URL are copied
    from the product: a later re-scrape may change them, but the order
    must keep the values that were actually charged.
    """
    items = []
    for cart_row in cart_queryset:
        product = cart_row.product
        if not product.is_published:
            # The product was unpublished between the add-to-cart and the
            # checkout: it cannot be ordered.
            continue
        source = product.scraped_source_product
        supplier_name = ""
        source_url = product.external_url
        compare_at_price = Decimal("0.000")
        if source is not None:
            supplier_name = (source.supplier.name if source.supplier else "")[:100]
            source_url = source_url or (source.source or "")[:500]
            compare_at_price = source.compare_at_price or Decimal("0.000")

        items.append(
            OrderItem(
                product=None,
                product_title=product.title[:255],
                quantity=cart_row.quantity,
                unit_price=product.selling_price,
                unit_cost=product.source_cost,
                currency="TND",
                currency_rate=Decimal("1"),
                supplier_name=supplier_name,
                source_url=source_url[:500],
                image_url=_first_image(product)[:500],
                compare_at_price=compare_at_price,
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
    store=None,
):
    """Create an order from the customer's cart.

    Returns ``(order, items)``. The cart is emptied on success, and the
    order is priced entirely from the database.
    """
    store = store or cart_store(session_key)
    rows = list(cart_lines(session_key, store))
    items = build_order_items(rows)
    if not items:
        raise ValueError("Panier vide ou produits indisponibles.")

    customer = Customer.objects.create(
        full_name=full_name[:200],
        phone=phone[:20],
        email=email[:254],
        governorate=governorate[:50],
        address=f"{delegation}, {address}".strip(", ")[:2000],
        store=store,
    )

    total_amount = sum((item.unit_price * item.quantity for item in items), Decimal("0.000"))
    total_cost = sum((item.line_cost_tnd() for item in items), Decimal("0.000"))

    order = Order.objects.create(
        customer=customer,
        store=store,
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

    The commission is recomputed on every transition: it is realized
    when the order reaches the delivered and paid state, and it goes
    back to zero when the order is returned. A COD order that never
    reached the customer must not leave a platform fee behind.
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

    # The platform fee follows the status: realized on delivery, zero
    # everywhere else.
    order.calculate_commissions(save=True)

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
