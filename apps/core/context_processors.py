"""Global context processors for Karthago Platform."""
from django.db.models import Sum, Count, Q
from apps.orders.constants import TUNISIAN_GOVERNORATES


def tunisian_governorates(request):
    """Make the 24 Tunisian governorates available in every template."""
    return {"governorates": TUNISIAN_GOVERNORATES}


def nav_categories(request):
    """Make the category list (with product counts) available in the nav.

    The navigation shows the categories on every page, so the list is
    provided by a context processor instead of being added by hand in each
    view.
    """
    try:
        from apps.catalog.models import Category

        categories = Category.objects.annotate(
            n=Count("products", filter=Q(products__is_active=True))
        ).order_by("-n", "name")
        return {"nav_categories": categories}
    except Exception:
        return {"nav_categories": []}


def cart_item_count(request):
    """Make the cart item count and total available in every template.

    The count drives the nav badge, the total drives the checkout summary.
    """
    try:
        from apps.orders.models import Cart
        from apps.orders.services import cart_total

        session_key = request.session.session_key or request.COOKIES.get("sessionid", "")
        if session_key:
            count = Cart.objects.filter(session_key=session_key).aggregate(
                total=Sum("quantity")
            )["total"] or 0
            return {"cart_item_count": count, "cart_total": cart_total(session_key)}
    except Exception:
        pass
    return {"cart_item_count": 0, "cart_total": 0}
