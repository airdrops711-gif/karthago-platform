"""Signals of the store lifecycle.

When the superadmin suspends a store, the platform must react
immediately: the storefront is closed by the tenant middleware, but the
search index still holds the documents of the store, and the cached
fragments of the homepage still show its products.

This module wires the ``Store`` model to:

* the eviction of the store documents from Meilisearch (deactivation)
  or their re-indexation (reactivation);
* the flush of the Redis cache fragments of the store.

The previous operational state is captured in ``pre_save`` — after the
write it is too late to read it back from the database.
"""
import logging

from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from .models import Store

logger = logging.getLogger(__name__)

#: Attribute used to carry the previous lifecycle state between the two
#: signal handlers.
_PREVIOUS_STATE_ATTR = "_previous_operational_state"


@receiver(pre_save, sender=Store)
def capture_previous_lifecycle(sender, instance, **kwargs):
    """Remember whether the store was operational before the write."""
    instance._previous_operational_state = _read_operational_state(instance)


@receiver(post_save, sender=Store)
def store_lifecycle_changed(sender, instance, created=False, **kwargs):
    """Propagate a lifecycle change to the search engine and the cache.

    The signal fires on every save of a store, so the previous state is
    compared with the new one: a rename must not trigger a full
    re-indexation of the catalogue.
    """
    if created:
        return

    # ``update_fields`` tells us which columns were written. When the
    # lifecycle columns are not among them, the operational status did
    # not change and there is nothing to propagate.
    update_fields = kwargs.get("update_fields")
    if update_fields is not None:
        watched = {"is_active", "status"}
        if not watched & set(update_fields):
            return

    was_operational = getattr(instance, _PREVIOUS_STATE_ATTR, None)
    if was_operational is None:
        return

    is_operational = _is_operational(instance)

    if was_operational == is_operational:
        return

    if is_operational:
        logger.info(
            "Store %s (%s) reactivated: re-indexing its catalogue.",
            instance.pk,
            instance.slug,
        )
        _reindex_store(instance)
    else:
        logger.info(
            "Store %s (%s) suspended: evicting its catalogue from the search index.",
            instance.pk,
            instance.slug,
        )
        _evict_store(instance)


def _is_operational(store):
    """True when a store may be browsed and searched."""
    return bool(store.is_active) and store.status == Store.STATUS_ACTIVE


def _read_operational_state(instance):
    """The operational state of the store as it is stored in the database.

    ``None`` when the row does not exist yet (a creation) or when the
    database cannot be read.
    """
    try:
        row = (
            Store.objects.filter(pk=instance.pk)
            .values("is_active", "status")
            .first()
        )
    except Exception as exc:  # database not ready
        logger.warning("Could not read the previous store state: %s", exc)
        return None

    if row is None:
        return None

    return bool(row["is_active"]) and row["status"] == Store.STATUS_ACTIVE


def _evict_store(instance):
    """Remove the documents of a suspended store from the search index."""
    try:
        from apps.catalog.tasks import evict_store_from_meilisearch

        # The task is asynchronous when a broker is available, and
        # synchronous otherwise (local dev, tests).
        evict_store_from_meilisearch.delay(instance.pk)
    except Exception as exc:
        logger.warning(
            "Could not schedule the eviction of store %s: %s", instance.pk, exc
        )
        try:
            from apps.catalog import search as search_module

            search_module.delete_store_documents(instance)
        except Exception as inner:
            logger.error("Eviction of store %s failed: %s", instance.pk, inner)


def _reindex_store(instance):
    """Push the catalogue of a reactivated store back to the search index."""
    try:
        from apps.catalog.tasks import reindex_store_in_meilisearch

        reindex_store_in_meilisearch.delay(instance.pk)
    except Exception as exc:
        logger.warning(
            "Could not schedule the re-indexation of store %s: %s", instance.pk, exc
        )
        try:
            from apps.catalog import search as search_module

            search_module.index_store(instance)
        except Exception as inner:
            logger.error("Re-indexation of store %s failed: %s", instance.pk, inner)
