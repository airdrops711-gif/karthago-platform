"""Template tags for building filter-preserving storefront URLs.

Every filter link in the sidebar/toolbar must keep the *other* active
filters. Rebuilding the query string by hand in the template is error
prone, so the `filter_url` tag does it from the current request.
"""
from django import template
from django.utils.http import urlencode
from django.utils.text import slugify

register = template.Library()

# Filters that describe the current page context rather than a facet.
_CONTEXT_KEYS = {"category", "page"}


@register.simple_tag(takes_context=True)
def filter_url(context, **overrides):
    """Build a URL that keeps the current filters, with `overrides` applied.

    Usage in a template::

        {% filter_url min_price="0" max_price="50" %}

    Passing a value of ``None`` removes that filter.
    """
    request = context.get("request")
    params = {}
    if request is not None:
        params = {
            key: value
            for key, value in request.GET.items()
            if key not in _CONTEXT_KEYS
        }
    for key, value in overrides.items():
        if value is None or value == "":
            params.pop(key, None)
        else:
            params[key] = value
    # Keep a stable order so the generated URLs are cache friendly.
    ordered = sorted(params.items())
    query = urlencode(ordered)
    path = request.path if request is not None else "/"
    return f"{path}?{query}" if query else path


@register.simple_tag(takes_context=True)
def category_url(context, slug):
    """URL of a category landing page, preserving the active facets.

    An empty slug returns the catalogue home, so the "Tous les produits"
    entry is a normal link and not a broken /category// path.

    The tenant categories are free text ("TV & Audio"), so the name is
    slugified to build a clean URL.
    """
    request = context.get("request")
    params = {}
    if request is not None:
        params = {
            key: value
            for key, value in request.GET.items()
            if key not in _CONTEXT_KEYS
        }
    ordered = sorted(params.items())
    query = urlencode(ordered)
    base = f"/category/{slugify(str(slug))}/" if slug else "/"
    return f"{base}?{query}" if query else base


@register.simple_tag(takes_context=True)
def is_filter_active(context, key, value):
    """True when the request carries the given filter value."""
    request = context.get("request")
    if request is None:
        return False
    return request.GET.get(key) == value


@register.filter
def get_item(mapping, key):
    """Dictionary lookup usable from a template."""
    if mapping is None:
        return None
    try:
        return mapping.get(key)
    except AttributeError:
        return None
