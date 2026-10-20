"""French labels for the order models.

Metadata only: the Django admin now speaks the same language as the
superadmin console. No table is touched.
"""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0005_alter_cart_product_alter_orderitem_product'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='cart',
            options={'ordering': ['-created_at'], 'verbose_name': 'Panier', 'verbose_name_plural': 'Paniers'},
        ),
        migrations.AlterModelOptions(
            name='customer',
            options={'verbose_name': 'Client', 'verbose_name_plural': 'Clients'},
        ),
        migrations.AlterModelOptions(
            name='delivery',
            options={'verbose_name': 'Livraison', 'verbose_name_plural': 'Livraisons'},
        ),
        migrations.AlterModelOptions(
            name='order',
            options={'ordering': ['-created_at'], 'verbose_name': 'Commande', 'verbose_name_plural': 'Commandes'},
        ),
        migrations.AlterModelOptions(
            name='orderevent',
            options={'ordering': ['-created_at'], 'verbose_name': 'Événement de commande', 'verbose_name_plural': 'Événements de commande'},
        ),
        migrations.AlterModelOptions(
            name='orderitem',
            options={'verbose_name': 'Ligne de commande', 'verbose_name_plural': 'Lignes de commande'},
        ),
    ]
