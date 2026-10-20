"""French labels for the catalogue models.

Metadata only: the Django admin now speaks the same language as the
superadmin console. No table is touched.
"""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('catalog', '0007_flagship_bootstrap'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='category',
            options={'ordering': ['name'], 'verbose_name': 'Catégorie', 'verbose_name_plural': 'Catégories'},
        ),
        migrations.AlterModelOptions(
            name='store',
            options={'ordering': ['name'], 'verbose_name': 'Boutique', 'verbose_name_plural': 'Boutiques'},
        ),
        migrations.AlterModelOptions(
            name='storeproduct',
            options={'ordering': ['-featured_priority', '-created_at'], 'verbose_name': 'Produit de boutique', 'verbose_name_plural': 'Produits de boutique'},
        ),
    ]
