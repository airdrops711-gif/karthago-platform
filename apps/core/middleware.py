"""Tenant resolution middleware.

The platform is multi-tenant at the row level over a single database.
Every request is resolved to exactly one tenant before any view runs, so
the views never have to guess which store the visitor is browsing.

Three cases:

* ``/s/<store_slug>/...`` — a vendor sub-store storefront. The tenant is
  the store named by the slug. An unknown or inactive slug resolves to
  ``None``, and the sub-store views answer 404.
* ``/dashboard/...`` — a signed-in vendor's own control panel. The
  tenant is the store owned by ``request.user``.
* anything else — the platform flagship, which owns ``/`` and the
  central scraped pool.
"""
from django.http import Http404


class TenantMiddleware:
    """Attach ``request.tenant_store`` and ``request.is_main_store``."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path_parts = request.path_info.strip("/").split("/")

        request.tenant_store = None
        request.is_main_store = True
        request.tenant_slug = ""

        # Sub-store storefront: /s/<store_slug>/...
        if len(path_parts) >= 2 and path_parts[0] == "s":
            store_slug = path_parts[1]
            request.tenant_slug = store_slug
            request.tenant_store = self._get_active_store(store_slug)
            request.is_main_store = False
            self._remember_tenant(request, store_slug)
        # Vendor authenticated dashboard session.
        elif request.path_info.startswith("/dashboard") and self._user(request):
            user = self._user(request)
            store = self._get_user_store(user)
            if store is None and user.is_staff:
                # A platform staff member without a store of their own
                # operates on the flagship.
                store = self._get_flagship_store()
            request.tenant_store = store
            request.is_main_store = store is not None and store.is_platform_default
            self._remember_tenant(request, store.slug if store is not None else "")
        # The platform consoles: the superadmin dashboard and the scraper
        # control plane always belong to the flagship.
        elif self._is_platform_page(request):
            request.tenant_store = self._get_flagship_store()
            request.is_main_store = True
            self._remember_tenant(request, "")
        # The flagship storefront pages: they always belong to the flagship.
        elif self._is_flagship_page(request):
            request.tenant_store = self._get_flagship_store()
            request.is_main_store = True
            self._remember_tenant(request, "")
        # Flat endpoints (cart, checkout, add-to-cart, HTMX fragments):
        # they belong to the tenant the visitor last browsed, so a cart
        # started on a sub-store stays on that sub-store.
        else:
            slug = self._remembered_tenant(request)
            store = self._get_active_store(slug) if slug else None
            request.tenant_store = store or self._get_flagship_store()
            request.is_main_store = store is None

        return self.get_response(request)

    # -- helpers ---------------------------------------------------------
    #: Session key holding the slug of the tenant the visitor browses.
    SESSION_TENANT_KEY = "tenant_slug"

    #: Path prefixes served by the flagship storefront.
    FLAGSHIP_PREFIXES = ("/catalogue/", "/category/", "/product/")

    #: Path prefixes served by the platform consoles.
    PLATFORM_PREFIXES = ("/admin-dashboard/", "/scraper/")

    @classmethod
    def _is_flagship_page(cls, request):
        """True for the pages of the flagship storefront (home included)."""
        path = request.path_info
        if path in ("", "/"):
            return True
        return any(path.startswith(prefix) for prefix in cls.FLAGSHIP_PREFIXES)

    @classmethod
    def _is_platform_page(cls, request):
        """True for the platform consoles (superadmin, scraper)."""
        return any(
            request.path_info.startswith(prefix) for prefix in cls.PLATFORM_PREFIXES
        )

    @classmethod
    def _remembered_tenant(cls, request):
        """The slug of the tenant the visitor browses, if any."""
        session = getattr(request, "session", None)
        if session is None:
            return ""
        return session.get(cls.SESSION_TENANT_KEY, "") or ""

    @classmethod
    def _remember_tenant(cls, request, slug):
        """Remember the tenant the visitor is browsing.

        The cart and the checkout live on flat URLs, so the session keeps
        the tenant of the last storefront page visited. Without it, adding
        a product to the cart from a sub-store would fall back to the
        flagship.
        """
        session = getattr(request, "session", None)
        if session is None:
            return
        if session.get(cls.SESSION_TENANT_KEY, "") != slug:
            session[cls.SESSION_TENANT_KEY] = slug
            session.modified = True

    @staticmethod
    def _user(request):
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            return None
        return user

    @staticmethod
    def _get_active_store(slug):
        from apps.catalog.models import Store

        if not slug:
            return None
        return (
            Store.objects.filter(slug=slug, is_active=True)
            .select_related("owner")
            .first()
        )

    @staticmethod
    def _get_user_store(user):
        from apps.catalog.models import Store

        store = getattr(user, "store", None)
        if store is None:
            return None
        if not store.is_active:
            return None
        return store

    @staticmethod
    def _get_flagship_store():
        from apps.catalog.models import Store

        return (
            Store.objects.filter(is_platform_default=True)
            .order_by("id")
            .first()
        )


def tenant_required(view_func):
    """Reject a request that does not resolve to a tenant.

    Used by the sub-store views: a request to ``/s/unknown-store/`` must
    not silently fall back to the flagship catalogue.

    The decorator works both on a plain function view and on a method of
    a class-based view. In the second case the wrapped callable
    receives the view instance as its first argument, so the request is
    taken from ``self.request`` and not from the first positional
    argument.
    """
    from functools import wraps

    @wraps(view_func)
    def _wrapped(*args, **kwargs):
        request = _extract_request(args)
        if request is None or getattr(request, "tenant_store", None) is None:
            raise Http404("Store introuvable")
        return view_func(*args, **kwargs)

    return _wrapped


def _extract_request(args):
    """Find the ``HttpRequest`` among the positional arguments.

    A function view is called as ``view(request, ...)``; a method of a
    class-based view is called as ``view(self, request, ...)`` and the
    request is also available as ``self.request``.
    """
    for candidate in args:
        if hasattr(candidate, "META") and hasattr(candidate, "GET"):
            return candidate
        inner = getattr(candidate, "request", None)
        if inner is not None and hasattr(inner, "META"):
            return inner
    return None
