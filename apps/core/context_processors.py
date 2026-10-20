"""Global context processors for Karthago Platform."""
from django.conf import settings
from django.db.models import Sum, Count, Q
from django.utils import translation

from apps.orders.constants import TUNISIAN_GOVERNORATES


def tenant_context(request):
    """Expose the resolved tenant to every template.

    The navbar shows the store name and links to the store's own
    catalogue, so the templates need to know whether the visitor is on
    the flagship or on a vendor sub-store.
    """
    store = getattr(request, "tenant_store", None)
    is_sub_store = bool(
        getattr(request, "tenant_slug", "")
        and store is not None
        and not store.is_platform_default
    )
    user = getattr(request, "user", None)
    is_staff = bool(user is not None and user.is_authenticated and user.is_staff)
    return {
        "tenant_store": store,
        "is_sub_store": is_sub_store,
        # The staff-only entries of the navbar (superadmin console,
        # dashboard) are hidden from the anonymous visitors.
        "is_staff": is_staff,
    }


def language_context(request):
    """Expose the current language and the direction of the page.

    The site speaks French and Tunisian Arabic. Arabic is written from
    right to left, so the whole layout has to be mirrored: the
    templates read ``dir`` and the ``rtl`` class from here.
    """
    code = translation.get_language() or "fr"
    return {
        "LANGUAGE_CODE": code,
        "LANGUAGES": settings.LANGUAGES,
        "language_dir": "rtl" if translation.get_language_bidi() else "ltr",
        "is_rtl": bool(translation.get_language_bidi()),
    }


def tunisian_governorates(request):
    """Make the 24 Tunisian governorates available in every template."""
    return {"governorates": TUNISIAN_GOVERNORATES}


def nav_categories(request):
    """Make the category list (with product counts) available in the nav.

    The navigation shows the categories on every page, so the list is
    provided by a context processor instead of being added by hand in
    each view. The categories are the ones of the tenant catalogue: a
    sub-store never shows the flagship's taxonomy.
    """
    try:
        from apps.catalog.tenancy import store_category_counts

        store = getattr(request, "tenant_store", None)
        if store is None:
            return {"nav_categories": []}
        return {"nav_categories": store_category_counts(store)}
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
