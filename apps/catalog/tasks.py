"""Celery tasks of the catalogue.

Two of them are wired to the lifecycle of a store: suspending a store
evicts its documents from the search index, reactivating it pushes them
back. Both degrade gracefully: when the search engine is unreachable
the task returns a report instead of raising, so the worker never dies
on a transient network error.
"""
import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(name="catalog.evict_store_from_meilisearch")
def evict_store_from_meilisearch(store_id):
    """Delete every document of a store from the search index.

    Returns a small report used by the console to tell the operator
    what happened.
    """
    from apps.catalog import search as search_module
    from apps.catalog.models import Store

    store = Store.objects.filter(pk=store_id).first()
    if store is None:
        return {"store_id": store_id, "deleted": 0, "ok": False}

    deleted = search_module.delete_store_documents(store)
    _flush_store_cache(store)
    return {"store_id": store_id, "deleted": deleted, "ok": True}


@shared_task(name="catalog.reindex_store_in_meilisearch")
def reindex_store_in_meilisearch(store_id):
    """Push the catalogue of a store back into the search index."""
    from apps.catalog import search as search_module
    from apps.catalog.models import Store

    store = Store.objects.filter(pk=store_id).first()
    if store is None:
        return {"store_id": store_id, "indexed": 0, "ok": False}

    indexed = search_module.index_store(store)
    _flush_store_cache(store)
    return {"store_id": store_id, "indexed": indexed, "ok": True}


def _flush_store_cache(store):
    """Drop the cached fragments that may still show the store.

    The cache is optional: when no cache backend is configured (local
    development, tests) the call is a no-op.
    """
    from django.core.cache import cache

    keys = [
        f"store:{store.pk}:catalogue",
        f"store:{store.pk}:featured",
        f"store:{store.pk}:categories",
        f"featured_showcase:{store.pk}",
    ]
    try:
        cache.delete_many(keys)
    except Exception as exc:
        logger.warning("Cache flush failed for store %s: %s", store.pk, exc)
