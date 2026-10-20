"""Core views including health check and the language switcher."""
from django.conf import settings
from django.http import Http404, HttpResponse, JsonResponse
from django.db import connection
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme


def healthz(request):
    """Kubernetes/OpenShift liveness and readiness probe endpoint."""
    db_ok = True
    try:
        connection.ensure_connection()
    except Exception:
        db_ok = False

    status = "ok" if db_ok else "degraded"
    return JsonResponse({"status": status, "database": db_ok}, status=200 if db_ok else 503)


#: The languages offered by the switcher.
SUPPORTED_LANGUAGES = ("fr", "ar")


def set_language(request):
    """Switch the language of the site (FR / AR).

    The language is stored in a cookie so that every page of the site
    — storefront, vendor console, superadmin console — is served in the
    chosen language. The visitor is sent back to the page they came
    from, so the switch never loses the context.
    """
    code = (request.POST.get("language") or request.GET.get("language") or "").strip()
    if code not in SUPPORTED_LANGUAGES:
        code = settings.LANGUAGE_CODE

    # The visitor is sent back to the page they came from. The target is
    # checked to make sure it is a local path: an external URL would
    # turn the switcher into an open redirect.
    next_url = request.POST.get("next") or request.GET.get("next") or "/"
    if not url_has_allowed_host_and_scheme(
        next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        next_url = "/"

    response = redirect(next_url)

    # The cookie is what ``LocaleMiddleware`` reads on the next request.
    response.set_cookie(
        settings.LANGUAGE_COOKIE_NAME,
        code,
        max_age=settings.LANGUAGE_COOKIE_AGE,
        samesite="Lax",
    )
    # The session is updated too: the vendor and superadmin consoles
    # render their own forms and need the same language.
    if hasattr(request, "session"):
        request.session["django_language"] = code

    return response


def store_logo(request, slug):
    """Serve the logo of a store (the image lives in the database).

    The logo is public: it appears in the nav of the storefront and in
    the search results, so it is served without authentication.
    """
    from apps.catalog.models import Store, StoreLogo

    store = Store.objects.filter(slug=slug).first()
    if store is None:
        raise Http404("Boutique introuvable")

    logo = StoreLogo.objects.filter(store=store).first()
    if logo is None:
        raise Http404("Logo introuvable")

    response = HttpResponse(bytes(logo.image), content_type=logo.content_type)
    # The logo changes only when the vendor uploads a new one.
    response["Cache-Control"] = "public, max-age=3600"
    response["ETag"] = f'"{logo.updated_at.timestamp()}"'
    return response

