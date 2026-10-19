"""Seed the scraper control plane with verified supplier sources.

Selectors below were validated against live HTML (HTTP 200 + element match).
Run:  python manage.py seed_sources
"""
from decimal import Decimal
from django.core.management.base import BaseCommand
from apps.scraper.models import ScrapedSource


# WooCommerce-style sources (quickk.tn, tunisia-tech.com)
WOOCONTAINER = ".product-grid-item"
WOOTITLE = ".wd-entities-title"
WOOPRICE = ".price"
WOOIMAGE = "img.attachment-full, img.attachment-large, img.attachment-woocommerce_thumbnail"

# FX rates to TND (approximate; update periodically)
RATES = {
    "TND": Decimal("1"),
    "EUR": Decimal("3.95"),
    "USD": Decimal("3.75"),
}


SOURCES = [
    # --- Tunisian local stores, prices already in TND ---
    {
        "name": "quickk_cuisine",
        "base_url": "https://www.quickk.tn/categorie-produit/cuisine/",
        "engine": ScrapedSource.ENGINE_STATIC,
        "product_container_selector": WOOCONTAINER,
        "title_selector": WOOTITLE,
        "price_selector": WOOPRICE,
        "stock_selector": "",
        "images_selector": WOOIMAGE,
        "category_name": "Cuisine",
        "currency": "TND",
        "currency_rate": RATES["TND"],
    },
    {
        "name": "quickk_maison",
        "base_url": "https://www.quickk.tn/categorie-produit/maison-confort/",
        "engine": ScrapedSource.ENGINE_STATIC,
        "product_container_selector": WOOCONTAINER,
        "title_selector": WOOTITLE,
        "price_selector": WOOPRICE,
        "stock_selector": "",
        "images_selector": WOOIMAGE,
        "category_name": "Maison & Confort",
        "currency": "TND",
        "currency_rate": RATES["TND"],
    },
    {
        "name": "quickk_sport",
        "base_url": "https://www.quickk.tn/categorie-produit/sport-fitness/",
        "engine": ScrapedSource.ENGINE_STATIC,
        "product_container_selector": WOOCONTAINER,
        "title_selector": WOOTITLE,
        "price_selector": WOOPRICE,
        "stock_selector": "",
        "images_selector": WOOIMAGE,
        "category_name": "Sport & Fitness",
        "currency": "TND",
        "currency_rate": RATES["TND"],
    },
    {
        # NOTE: /auto-et-moto/auto/ renders "Aucun produit" on the live site,
        # so the general "divers" category is used instead.
        "name": "quickk_divers",
        "base_url": "https://www.quickk.tn/categorie-produit/divers/",
        "engine": ScrapedSource.ENGINE_STATIC,
        "product_container_selector": WOOCONTAINER,
        "title_selector": WOOTITLE,
        "price_selector": WOOPRICE,
        "stock_selector": "",
        "images_selector": WOOIMAGE,
        "category_name": "Divers",
        "currency": "TND",
        "currency_rate": RATES["TND"],
    },
    {
        "name": "quickk_outils",
        "base_url": "https://www.quickk.tn/categorie-produit/outils-et-bricolage/",
        "engine": ScrapedSource.ENGINE_STATIC,
        "product_container_selector": WOOCONTAINER,
        "title_selector": WOOTITLE,
        "price_selector": WOOPRICE,
        "stock_selector": "",
        "images_selector": WOOIMAGE,
        "category_name": "Outils & Bricolage",
        "currency": "TND",
        "currency_rate": RATES["TND"],
    },
    {
        "name": "quickk_loisir",
        "base_url": "https://www.quickk.tn/categorie-produit/jouets-loisir/",
        "engine": ScrapedSource.ENGINE_STATIC,
        "product_container_selector": WOOCONTAINER,
        "title_selector": WOOTITLE,
        "price_selector": WOOPRICE,
        "stock_selector": "",
        "images_selector": WOOIMAGE,
        "category_name": "Jouets & Loisir",
        "currency": "TND",
        "currency_rate": RATES["TND"],
    },
    {
        "name": "quickk_shop",
        "base_url": "https://www.quickk.tn/shop/",
        "engine": ScrapedSource.ENGINE_STATIC,
        "product_container_selector": WOOCONTAINER,
        "title_selector": WOOTITLE,
        "price_selector": WOOPRICE,
        "stock_selector": "",
        "images_selector": WOOIMAGE,
        "category_name": "General",
        "currency": "TND",
        "currency_rate": RATES["TND"],
    },
    # --- Tunisian tech store, prices in EUR ---
    {
        "name": "tunisia_tech",
        "base_url": "https://tunisia-tech.com/",
        "engine": ScrapedSource.ENGINE_STATIC,
        "product_container_selector": WOOCONTAINER,
        "title_selector": WOOTITLE,
        "price_selector": WOOPRICE,
        "stock_selector": "",
        "images_selector": WOOIMAGE,
        "category_name": "Electronics",
        "currency": "EUR",
        "currency_rate": RATES["EUR"],
    },
    {
        "name": "tunisia_tech_telephonie",
        "base_url": "https://tunisia-tech.com/categorie-produit/telephonie/",
        "engine": ScrapedSource.ENGINE_STATIC,
        "product_container_selector": WOOCONTAINER,
        "title_selector": WOOTITLE,
        "price_selector": WOOPRICE,
        "stock_selector": "",
        "images_selector": WOOIMAGE,
        "category_name": "Electronics",
        "currency": "EUR",
        "currency_rate": RATES["EUR"],
    },
    {
        "name": "tunisia_tech_informatique",
        "base_url": "https://tunisia-tech.com/categorie-produit/informatique/",
        "engine": ScrapedSource.ENGINE_STATIC,
        "product_container_selector": WOOCONTAINER,
        "title_selector": WOOTITLE,
        "price_selector": WOOPRICE,
        "stock_selector": "",
        "images_selector": WOOIMAGE,
        "category_name": "Electronics",
        "currency": "EUR",
        "currency_rate": RATES["EUR"],
    },
    # --- International sources, prices converted to TND ---
    {
        "name": "aliexpress_electronics",
        "base_url": "https://www.aliexpress.com/wholesale?SearchText=phone",
        "engine": ScrapedSource.ENGINE_STATIC,
        "product_container_selector": "div[class*='search-item-card-wrapper-gallery']",
        "title_selector": "[class*='us--title--']",
        "price_selector": "[class*='us--price--']",
        "stock_selector": "",
        "images_selector": "img[class*='images--item--']",
        "category_name": "Electronics",
        "currency": "EUR",
        "currency_rate": RATES["EUR"],
    },
    {
        "name": "aliexpress_home",
        "base_url": "https://www.aliexpress.com/wholesale?SearchText=home+decor",
        "engine": ScrapedSource.ENGINE_STATIC,
        "product_container_selector": "div[class*='search-item-card-wrapper-gallery']",
        "title_selector": "[class*='us--title--']",
        "price_selector": "[class*='us--price--']",
        "stock_selector": "",
        "images_selector": "img[class*='images--item--']",
        "category_name": "Home & Garden",
        "currency": "EUR",
        "currency_rate": RATES["EUR"],
    },
    {
        "name": "walmart_electronics",
        "base_url": "https://www.walmart.com/browse/electronics",
        "engine": ScrapedSource.ENGINE_STATIC,
        "product_container_selector": "[data-item-id]",
        "title_selector": "[data-automation-id='product-title'], h3",
        # The a11y price node keeps the decimal point ("Price $84.28").
        # The visual node renders cents without a separator ("$8428").
        "price_selector": "[data-testid='unified-global-product-price-a11y-text']",
        "stock_selector": "",
        "images_selector": "img[data-testid='productTileImage']",
        "category_name": "Electronics",
        "currency": "USD",
        "currency_rate": RATES["USD"],
    },
]


class Command(BaseCommand):
    help = "Seed/refresh the scraper source catalogue with validated sources."

    def add_arguments(self, parser):
        parser.add_argument(
            "--prune",
            action="store_true",
            help="Delete sources that are no longer part of the validated catalogue.",
        )

    def handle(self, *args, **options):
        created, updated = 0, 0
        for data in SOURCES:
            name = data["name"]
            defaults = {k: v for k, v in data.items() if k != "name"}
            obj, was_created = ScrapedSource.objects.update_or_create(
                name=name, defaults=defaults
            )
            if was_created:
                created += 1
                self.stdout.write(self.style.SUCCESS(f"  created  {name}"))
            else:
                updated += 1
                self.stdout.write(f"  updated  {name}")

        pruned = 0
        if options.get("prune"):
            known = {d["name"] for d in SOURCES}
            for stale in ScrapedSource.objects.exclude(name__in=known):
                self.stdout.write(self.style.WARNING(f"  pruned   {stale.name}"))
                stale.delete()
                pruned += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"\nSources ready: {created} created, {updated} updated, "
                f"{pruned} pruned, {ScrapedSource.objects.count()} total"
            )
        )
