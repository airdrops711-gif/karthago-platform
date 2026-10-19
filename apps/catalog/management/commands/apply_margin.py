"""Apply the flat margin to every product of the catalogue.

The storefront sells at a single rule: the supplier cost plus a 10% markup
and no fixed fee. This command re-applies that rule to the whole catalogue
without hitting the suppliers again.

    python manage.py apply_margin
    python manage.py apply_margin --markup 12 --fee 0
"""
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.catalog.models import MarginRule, Product


class Command(BaseCommand):
    help = "Recompute the retail price of every product from the default margin rule."

    def add_arguments(self, parser):
        parser.add_argument(
            "--markup",
            type=str,
            default="10.00",
            help="Markup percentage applied to the supplier cost (default 10.00).",
        )
        parser.add_argument(
            "--fee",
            type=str,
            default="0.000",
            help="Fixed margin fee added in TND (default 0.000).",
        )

    def handle(self, *args, **options):
        markup = Decimal(options["markup"])
        fee = Decimal(options["fee"])

        with transaction.atomic():
            rule, _ = MarginRule.objects.update_or_create(
                name="Default",
                defaults={"markup_percent": markup, "fixed_margin_fee": fee},
            )

            products = Product.objects.all()
            total = products.count()
            for product in products.iterator(chunk_size=500):
                product.margin_rule = rule
                product.markup_percent = markup
                product.fixed_margin_fee = fee
                product.save()

        self.stdout.write(
            self.style.SUCCESS(
                f"Applied {markup}% markup (+{fee} DT) to {total} products."
            )
        )
