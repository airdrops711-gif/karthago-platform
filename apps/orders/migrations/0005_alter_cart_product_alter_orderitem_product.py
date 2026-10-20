"""Re-point the cart and the order lines to the tenant catalogue.

``Cart.product`` and ``OrderItem.product`` used to reference the central
``catalog.Product`` row. They now reference a ``catalog.StoreProduct`` —
the row of the store that actually sells the product.

The legacy rows still hold the ids of the old table, so the values are
remapped through the ``scraped_source_product`` link of the tenant
catalogue:

* a cart line whose product was cloned into the store points at that
  clone;
* a cart line whose product is gone is dropped — a cart is a transient
  session and must never block a migration;
* an order line keeps its history: the product reference is simply
  cleared when the product is not in the tenant catalogue, because the
  price snapshot on the line is the historical truth.

Ordering matters. PostgreSQL validates the existing rows when
``ADD CONSTRAINT`` creates a foreign key, so the old constraint has to
be dropped *before* the ids are rewritten. The migration therefore runs
in three steps:

1. drop the legacy constraints (``db_constraint=False``),
2. remap the ids,
3. re-point the fields and restore the constraints.

Step 1 and step 3 are both ``AlterField`` operations: ``db_constraint``
is part of the field deconstruction, so Django notices the change and
emits the matching ``DROP CONSTRAINT`` / ``ADD CONSTRAINT``.
"""
import django.db.models.deletion
from django.db import migrations, models


def _clone_map(StoreProduct, store_id):
    """Map a central product id to its clone inside one store."""
    clones = {}
    for source_id, clone_id in StoreProduct.objects.filter(
        store_id=store_id, scraped_source_product__isnull=False
    ).values_list("scraped_source_product_id", "id"):
        clones[source_id] = clone_id
    return clones


def remap_product_ids(apps, schema_editor):
    Cart = apps.get_model("orders", "Cart")
    Order = apps.get_model("orders", "Order")
    OrderItem = apps.get_model("orders", "OrderItem")
    Store = apps.get_model("catalog", "Store")
    StoreProduct = apps.get_model("catalog", "StoreProduct")

    flagship = (
        Store.objects.filter(is_platform_default=True).order_by("id").first()
        or Store.objects.order_by("id").first()
    )
    flagship_id = flagship.id if flagship is not None else None

    # One clone map per store that actually holds rows.
    store_ids = set(
        Cart.objects.exclude(store_id__isnull=True).values_list("store_id", flat=True)
    )
    store_ids |= set(
        Order.objects.exclude(store_id__isnull=True).values_list("store_id", flat=True)
    )
    if flagship_id is not None:
        store_ids.add(flagship_id)
    clone_maps = {store_id: _clone_map(StoreProduct, store_id) for store_id in store_ids}

    def clones_for(store_id):
        if store_id in clone_maps:
            return clone_maps[store_id]
        # No tenant on the row: the legacy data belonged to the flagship.
        return clone_maps.get(flagship_id, {})

    # --- the cart lines ---------------------------------------------------
    # The cart is unique on (session_key, product): two legacy rows of the
    # same session can collapse onto the same clone, so the duplicates are
    # merged (quantities added) instead of violating the constraint.
    dropped = 0
    remapped = 0
    for cart in Cart.objects.all().iterator():
        if cart.product_id is None:
            continue
        clone_id = clones_for(cart.store_id).get(cart.product_id)
        if clone_id is None:
            cart.delete()
            dropped += 1
            continue
        twin = (
            Cart.objects.filter(session_key=cart.session_key, product_id=clone_id)
            .exclude(pk=cart.pk)
            .first()
        )
        if twin is not None:
            twin.quantity += cart.quantity
            twin.save(update_fields=["quantity"])
            cart.delete()
            dropped += 1
            continue
        Cart.objects.filter(pk=cart.pk).update(product_id=clone_id)
        remapped += 1

    # --- the order lines --------------------------------------------------
    cleared = 0
    remapped_items = 0
    for item in OrderItem.objects.all().iterator():
        if item.product_id is None:
            continue
        store_id = item.order.store_id
        clone_id = clones_for(store_id).get(item.product_id)
        if clone_id is None:
            OrderItem.objects.filter(pk=item.pk).update(product_id=None)
            cleared += 1
        else:
            OrderItem.objects.filter(pk=item.pk).update(product_id=clone_id)
            remapped_items += 1

    print(
        f"cart rows remapped: {remapped}, dropped: {dropped}; "
        f"order lines remapped: {remapped_items}, cleared: {cleared}"
    )


def restore_nothing(apps, schema_editor):
    """The ids are not reversible: the rollback keeps the tenant rows."""


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0007_flagship_bootstrap"),
        ("orders", "0004_cart_store_customer_store_order_store"),
    ]

    operations = [
        # --- 1. drop the legacy constraints --------------------------------
        migrations.AlterField(
            model_name="cart",
            name="product",
            field=models.ForeignKey(
                db_constraint=False,
                on_delete=django.db.models.deletion.CASCADE,
                to="catalog.product",
            ),
        ),
        migrations.AlterField(
            model_name="orderitem",
            name="product",
            field=models.ForeignKey(
                blank=True,
                db_constraint=False,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="order_items",
                to="catalog.product",
            ),
        ),
        # --- 2. remap the ids while nothing constrains them -----------------
        migrations.RunPython(remap_product_ids, restore_nothing),
        # --- 3. re-point the fields and restore the constraints ------------
        migrations.AlterField(
            model_name="cart",
            name="product",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE, to="catalog.storeproduct"
            ),
        ),
        migrations.AlterField(
            model_name="orderitem",
            name="product",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="order_items",
                to="catalog.storeproduct",
            ),
        ),
    ]
