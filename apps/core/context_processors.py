"""Global context processors for Karthago Platform."""
from django.db.models import Sum
from apps.orders.constants import TUNISIAN_GOVERNORATES


def tunisian_governorates(request):
    """Make the 24 Tunisian governorates available in every template."""
    return {"governorates": TUNISIAN_GOVERNORATES}


def cart_item_count(request):
    """Make the cart item count available in every template (nav badge)."""
    try:
        from apps.orders.models import Cart
        session_key = request.session.session_key or request.COOKIES.get("sessionid", "")
        if session_key:
            count = Cart.objects.filter(session_key=session_key).aggregate(
                total=Sum("quantity")
            )["total"] or 0
            return {"cart_item_count": count}
    except Exception:
        pass
    return {"cart_item_count": 0}
