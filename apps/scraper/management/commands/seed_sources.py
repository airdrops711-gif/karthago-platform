"""Seed the scraper control plane with verified supplier sources.

Every selector below was validated against live HTML on 2026-10-19 with a
200 response and a real element match. See the `karthago-scraper-sources`
skill for the full evidence.

Run:  python manage.py seed_sources
"""
from decimal import Decimal
from django.core.management.base import BaseCommand
from apps.catalog.category_icons import icon_for
from apps.scraper.models import ScrapedSource


# FX rates to TND (approximate; update periodically)
RATES = {
    "TND": Decimal("1"),
    "EUR": Decimal("3.95"),
    "USD": Decimal("3.75"),
}

# --------------------------------------------------------------------------
# PrestaShop (tunisianet.com.tn, twenty.tn)
# --------------------------------------------------------------------------
PRESTASHOP = {
    "engine": ScrapedSource.ENGINE_STATIC,
    "product_container_selector": "article.product-miniature",
    "title_selector": "h2.product-title",
    "price_strategy": "first",
    "price_text_mode": "deep",
    "currency": "TND",
    "currency_rate": RATES["TND"],
    "sync_frequency_hours": 6,
}

# --------------------------------------------------------------------------
# Magento 2 (wamia.tn) — Cloudflare-protected.
#
# STATUS: parked. wamia.tn answers 403 with a `cf-mitigated: challenge`
# interstitial to every direct request (agent box, OpenShift pod, curl_cffi
# TLS impersonation, public CORS proxies). The Firecrawl fallback is
# currently rate-limited on the keyless free tier, so the source cannot be
# scraped at all right now. It stays seeded (with its verified selectors)
# and simply inactive, so it can be re-enabled the moment a working
# transport is available.
# --------------------------------------------------------------------------
MAGENTO = {
    "engine": ScrapedSource.ENGINE_STATIC,
    "product_container_selector": "li.product",
    "title_selector": "a.product-item-link",
    "price_selector": "span.price",
    "price_strategy": "first",
    "price_text_mode": "deep",
    "currency": "TND",
    "currency_rate": RATES["TND"],
    "sync_frequency_hours": 12,
    "is_active": False,
}

# --------------------------------------------------------------------------
# Shopify (noonclo.com) — the JSON catalogue API is the primary path
# --------------------------------------------------------------------------
SHOPIFY = {
    "engine": ScrapedSource.ENGINE_STATIC,
    "product_container_selector": ".grid__item.grid-product",
    "title_selector": ".grid-product__title",
    "price_strategy": "first",
    "price_text_mode": "shallow",
    "currency": "TND",
    "currency_rate": RATES["TND"],
    "sync_frequency_hours": 6,
}


SOURCES = [
    # --- Tunisianet: 66 top departments, PrestaShop -------------------
    {
        "name": "tunisianet_ordinateurs_portables",
        "base_url": "https://www.tunisianet.com.tn/702-ordinateur-portable",
        **PRESTASHOP,
        "price_selector": "span.price",
        "compare_at_price_selector": "span.regular-price",
        "stock_selector": "span.in-stock",
        "images_selector": "img.thumbnail-img",
        "pagination_next_selector": "nav.pagination a[rel=next]",
        "category_name": "Ordinateurs Portables",
    },
    {
        "name": "tunisianet_informatique",
        "base_url": "https://www.tunisianet.com.tn/700-accessoires-et-peripheriques",
        **PRESTASHOP,
        "price_selector": "span.price",
        "compare_at_price_selector": "span.regular-price",
        "stock_selector": "span.in-stock",
        "images_selector": "img.thumbnail-img",
        "pagination_next_selector": "nav.pagination a[rel=next]",
        "category_name": "Informatique & Accessoires",
    },
    {
        "name": "tunisianet_telephonie",
        "base_url": "https://www.tunisianet.com.tn/377-telephone-portable-tunisie",
        **PRESTASHOP,
        "price_selector": "span.price",
        "compare_at_price_selector": "span.regular-price",
        "stock_selector": "span.in-stock",
        "images_selector": "img.thumbnail-img",
        "pagination_next_selector": "nav.pagination a[rel=next]",
        "category_name": "Téléphones Portables",
    },
    {
        "name": "tunisianet_smartphones",
        "base_url": "https://www.tunisianet.com.tn/596-smartphone-tunisie",
        **PRESTASHOP,
        "price_selector": "span.price",
        "compare_at_price_selector": "span.regular-price",
        "stock_selector": "span.in-stock",
        "images_selector": "img.thumbnail-img",
        "pagination_next_selector": "nav.pagination a[rel=next]",
        "category_name": "Smartphones",
    },
    {
        "name": "tunisianet_electromenager",
        "base_url": "https://www.tunisianet.com.tn/521-electromenager-tunisie",
        **PRESTASHOP,
        "price_selector": "span.price",
        "compare_at_price_selector": "span.regular-price",
        "stock_selector": "span.in-stock",
        "images_selector": "img.thumbnail-img",
        "pagination_next_selector": "nav.pagination a[rel=next]",
        "category_name": "Électroménager",
    },
    {
        "name": "tunisianet_cuisine",
        "base_url": "https://www.tunisianet.com.tn/522-petit-electromenager-tunisie-cuisine",
        **PRESTASHOP,
        "price_selector": "span.price",
        "compare_at_price_selector": "span.regular-price",
        "stock_selector": "span.in-stock",
        "images_selector": "img.thumbnail-img",
        "pagination_next_selector": "nav.pagination a[rel=next]",
        "category_name": "Cuisine & Électroménager",
    },
    {
        "name": "tunisianet_tv_son",
        "base_url": "https://www.tunisianet.com.tn/369-vente-tv-samsung-led-tunisie",
        **PRESTASHOP,
        "price_selector": "span.price",
        "compare_at_price_selector": "span.regular-price",
        "stock_selector": "span.in-stock",
        "images_selector": "img.thumbnail-img",
        "pagination_next_selector": "nav.pagination a[rel=next]",
        "category_name": "TV & Audio",
    },
    {
        "name": "tunisianet_jeux",
        "base_url": "https://www.tunisianet.com.tn/466-console-de-jeux",
        **PRESTASHOP,
        "price_selector": "span.price",
        "compare_at_price_selector": "span.regular-price",
        "stock_selector": "span.in-stock",
        "images_selector": "img.thumbnail-img",
        "pagination_next_selector": "nav.pagination a[rel=next]",
        "category_name": "Consoles & Jeux",
    },
    {
        "name": "tunisianet_bureau",
        "base_url": "https://www.tunisianet.com.tn/649-accessoires-de-bureau",
        **PRESTASHOP,
        "price_selector": "span.price",
        "compare_at_price_selector": "span.regular-price",
        "stock_selector": "span.in-stock",
        "images_selector": "img.thumbnail-img",
        "pagination_next_selector": "nav.pagination a[rel=next]",
        "category_name": "Fournitures de Bureau",
    },
    {
        "name": "tunisianet_mobilite",
        "base_url": "https://www.tunisianet.com.tn/761-protection-mobilite-accessoires",
        **PRESTASHOP,
        "price_selector": "span.price",
        "compare_at_price_selector": "span.regular-price",
        "stock_selector": "span.in-stock",
        "images_selector": "img.thumbnail-img",
        "pagination_next_selector": "nav.pagination a[rel=next]",
        "category_name": "Mobilité & Transport",
    },
    # --- Twenty: 21 root departments, PrestaShop --------------------
    #
    # Twenty's root department pages hold only a handful of products each
    # (5 for Informatique, 1 for Electromenager). The level-2 pages hold
    # the real catalogue, so both levels are seeded: the root gives the
    # department identity, the level-2 pages give the volume.
    {
        "name": "twenty_informatique",
        "base_url": "https://www.twenty.tn/fr/159-informatique",
        **PRESTASHOP,
        "price_selector": "span.product-price",
        "compare_at_price_selector": "span.regular-price",
        "stock_selector": "",
        "images_selector": "img[data-src]",
        "pagination_next_selector": "",
        "category_name": "Informatique",
    },
    {
        "name": "twenty_cables",
        "base_url": "https://www.twenty.tn/fr/164-cables",
        **PRESTASHOP,
        "price_selector": "span.product-price",
        "compare_at_price_selector": "span.regular-price",
        "stock_selector": "",
        "images_selector": "img[data-src]",
        "pagination_next_selector": "",
        "category_name": "Câbles & Adaptateurs",
    },
    {
        "name": "twenty_adaptateurs",
        "base_url": "https://www.twenty.tn/fr/166-adaptateurs",
        **PRESTASHOP,
        "price_selector": "span.product-price",
        "compare_at_price_selector": "span.regular-price",
        "stock_selector": "",
        "images_selector": "img[data-src]",
        "pagination_next_selector": "",
        "category_name": "Adaptateurs",
    },
    {
        "name": "twenty_ecouteurs",
        "base_url": "https://www.twenty.tn/fr/145-ecouteurs",
        **PRESTASHOP,
        "price_selector": "span.product-price",
        "compare_at_price_selector": "span.regular-price",
        "stock_selector": "",
        "images_selector": "img[data-src]",
        "pagination_next_selector": "",
        "category_name": "Écouteurs & Casques",
    },
    {
        "name": "twenty_haut_parleurs",
        "base_url": "https://www.twenty.tn/fr/146-haut-parleurs",
        **PRESTASHOP,
        "price_selector": "span.product-price",
        "compare_at_price_selector": "span.regular-price",
        "stock_selector": "",
        "images_selector": "img[data-src]",
        "pagination_next_selector": "",
        "category_name": "Haut-parleurs",
    },
    {
        "name": "twenty_electromenager",
        "base_url": "https://www.twenty.tn/fr/255-electromenager",
        **PRESTASHOP,
        "price_selector": "span.product-price",
        "compare_at_price_selector": "span.regular-price",
        "stock_selector": "",
        "images_selector": "img[data-src]",
        "pagination_next_selector": "",
        "category_name": "Électroménager",
    },
    {
        "name": "twenty_sante_beaute",
        "base_url": "https://www.twenty.tn/fr/29-sante-beaute",
        **PRESTASHOP,
        "price_selector": "span.product-price",
        "compare_at_price_selector": "span.regular-price",
        "stock_selector": "",
        "images_selector": "img[data-src]",
        "pagination_next_selector": "",
        "category_name": "Santé & Beauté",
    },
    {
        "name": "twenty_mode_bijoux",
        "base_url": "https://www.twenty.tn/fr/32-mode-bijoux",
        **PRESTASHOP,
        "price_selector": "span.product-price",
        "compare_at_price_selector": "span.regular-price",
        "stock_selector": "",
        "images_selector": "img[data-src]",
        "pagination_next_selector": "",
        "category_name": "Mode & Bijoux",
    },
    {
        "name": "twenty_maison_bureau",
        "base_url": "https://www.twenty.tn/fr/33-maison-et-bureau",
        **PRESTASHOP,
        "price_selector": "span.product-price",
        "compare_at_price_selector": "span.regular-price",
        "stock_selector": "",
        "images_selector": "img[data-src]",
        "pagination_next_selector": "",
        "category_name": "Maison & Bureau",
    },
    {
        "name": "twenty_decoration",
        "base_url": "https://www.twenty.tn/fr/45-decoration",
        **PRESTASHOP,
        "price_selector": "span.product-price",
        "compare_at_price_selector": "span.regular-price",
        "stock_selector": "",
        "images_selector": "img[data-src]",
        "pagination_next_selector": "",
        "category_name": "Décoration",
    },
    {
        "name": "twenty_sport",
        "base_url": "https://www.twenty.tn/fr/272-sport",
        **PRESTASHOP,
        "price_selector": "span.product-price",
        "compare_at_price_selector": "span.regular-price",
        "stock_selector": "",
        "images_selector": "img[data-src]",
        "pagination_next_selector": "",
        "category_name": "Sport",
    },
    {
        "name": "twenty_jouets",
        "base_url": "https://www.twenty.tn/fr/113-jouets-jeux",
        **PRESTASHOP,
        "price_selector": "span.product-price",
        "compare_at_price_selector": "span.regular-price",
        "stock_selector": "",
        "images_selector": "img[data-src]",
        "pagination_next_selector": "",
        "category_name": "Jouets & Jeux",
    },
    {
        "name": "twenty_auto_moto",
        "base_url": "https://www.twenty.tn/fr/175-auto-moto",
        **PRESTASHOP,
        "price_selector": "span.product-price",
        "compare_at_price_selector": "span.regular-price",
        "stock_selector": "",
        "images_selector": "img[data-src]",
        "pagination_next_selector": "",
        "category_name": "Auto & Moto",
    },
    {
        "name": "twenty_animalerie",
        "base_url": "https://www.twenty.tn/fr/171-animalerie",
        **PRESTASHOP,
        "price_selector": "span.product-price",
        "compare_at_price_selector": "span.regular-price",
        "stock_selector": "",
        "images_selector": "img[data-src]",
        "pagination_next_selector": "",
        "category_name": "Animalerie",
    },
    {
        "name": "twenty_superette",
        "base_url": "https://www.twenty.tn/fr/31-superette",
        **PRESTASHOP,
        "price_selector": "span.product-price",
        "compare_at_price_selector": "span.regular-price",
        "stock_selector": "",
        "images_selector": "img[data-src]",
        "pagination_next_selector": "",
        "category_name": "Supérette & Épicerie",
    },
    {
        "name": "twenty_eclairage",
        "base_url": "https://www.twenty.tn/fr/188-eclairage",
        **PRESTASHOP,
        "price_selector": "span.product-price",
        "compare_at_price_selector": "span.regular-price",
        "stock_selector": "",
        "images_selector": "img[data-src]",
        "pagination_next_selector": "",
        "category_name": "Éclairage",
    },
    {
        "name": "twenty_gaming",
        "base_url": "https://www.twenty.tn/fr/189-gaming",
        **PRESTASHOP,
        "price_selector": "span.product-price",
        "compare_at_price_selector": "span.regular-price",
        "stock_selector": "",
        "images_selector": "img[data-src]",
        "pagination_next_selector": "",
        "category_name": "Gaming",
    },
    {
        "name": "twenty_fournitures_bureau",
        "base_url": "https://www.twenty.tn/fr/382-fournitures-de-bureau",
        **PRESTASHOP,
        "price_selector": "span.product-price",
        "compare_at_price_selector": "span.regular-price",
        "stock_selector": "",
        "images_selector": "img[data-src]",
        "pagination_next_selector": "",
        "category_name": "Fournitures de Bureau",
    },
    {
        "name": "twenty_made_in_tunisia",
        "base_url": "https://www.twenty.tn/fr/58-made-in-tunisia",
        **PRESTASHOP,
        "price_selector": "span.product-price",
        "compare_at_price_selector": "span.regular-price",
        "stock_selector": "",
        "images_selector": "img[data-src]",
        "pagination_next_selector": "",
        "category_name": "Made in Tunisia",
    },
    {
        "name": "twenty_instruments_musique",
        "base_url": "https://www.twenty.tn/fr/102-instruments-de-musique",
        **PRESTASHOP,
        "price_selector": "span.product-price",
        "compare_at_price_selector": "span.regular-price",
        "stock_selector": "",
        "images_selector": "img[data-src]",
        "pagination_next_selector": "",
        "category_name": "Instruments de Musique",
    },
    {
        "name": "twenty_telephone_tablette",
        "base_url": "https://www.twenty.tn/fr/27-telephone-tablette-tunisie",
        **PRESTASHOP,
        "price_selector": "span.product-price",
        "compare_at_price_selector": "span.regular-price",
        "stock_selector": "",
        "images_selector": "img[data-src]",
        "pagination_next_selector": "",
        "category_name": "Téléphones & Tablettes",
    },
    {
        "name": "twenty_chaussures",
        "base_url": "https://www.twenty.tn/fr/252-chaussures",
        **PRESTASHOP,
        "price_selector": "span.product-price",
        "compare_at_price_selector": "span.regular-price",
        "stock_selector": "",
        "images_selector": "img[data-src]",
        "pagination_next_selector": "",
        "category_name": "Chaussures",
    },
    {
        "name": "twenty_sacs",
        "base_url": "https://www.twenty.tn/fr/65-sacs",
        **PRESTASHOP,
        "price_selector": "span.product-price",
        "compare_at_price_selector": "span.regular-price",
        "stock_selector": "",
        "images_selector": "img[data-src]",
        "pagination_next_selector": "",
        "category_name": "Sacs",
    },
    {
        "name": "twenty_bijoux",
        "base_url": "https://www.twenty.tn/fr/60-bijoux",
        **PRESTASHOP,
        "price_selector": "span.product-price",
        "compare_at_price_selector": "span.regular-price",
        "stock_selector": "",
        "images_selector": "img[data-src]",
        "pagination_next_selector": "",
        "category_name": "Bijoux",
    },
    # --- Wamia: 18 top categories, Magento 2, Cloudflare-protected ---
    {
        "name": "wamia_electromenager",
        "base_url": "https://www.wamia.tn/electromenager-tunisie.html",
        **MAGENTO,
        "compare_at_price_selector": "span.old-price, span.special-price",
        "stock_selector": "",
        "images_selector": "img.product-image-photo",
        "pagination_next_selector": "a.next",
        "category_name": "Électroménager",
    },
    {
        "name": "wamia_high_tech",
        "base_url": "https://www.wamia.tn/high-tech.html",
        **MAGENTO,
        "compare_at_price_selector": "span.old-price, span.special-price",
        "stock_selector": "",
        "images_selector": "img.product-image-photo",
        "pagination_next_selector": "a.next",
        "category_name": "High-Tech",
    },
    {
        "name": "wamia_informatique",
        "base_url": "https://www.wamia.tn/informatique.html",
        **MAGENTO,
        "compare_at_price_selector": "span.old-price, span.special-price",
        "stock_selector": "",
        "images_selector": "img.product-image-photo",
        "pagination_next_selector": "a.next",
        "category_name": "Informatique",
    },
    {
        "name": "wamia_mode",
        "base_url": "https://www.wamia.tn/mode.html",
        **MAGENTO,
        "compare_at_price_selector": "span.old-price, span.special-price",
        "stock_selector": "",
        "images_selector": "img.product-image-photo",
        "pagination_next_selector": "a.next",
        "category_name": "Mode",
    },
    {
        "name": "wamia_cuisine",
        "base_url": "https://www.wamia.tn/cuisine.html",
        **MAGENTO,
        "compare_at_price_selector": "span.old-price, span.special-price",
        "stock_selector": "",
        "images_selector": "img.product-image-photo",
        "pagination_next_selector": "a.next",
        "category_name": "Cuisine",
    },
    {
        "name": "wamia_decoration_maison",
        "base_url": "https://www.wamia.tn/decoration-maison.html",
        **MAGENTO,
        "compare_at_price_selector": "span.old-price, span.special-price",
        "stock_selector": "",
        "images_selector": "img.product-image-photo",
        "pagination_next_selector": "a.next",
        "category_name": "Décoration Maison",
    },
    {
        "name": "wamia_sport_loisir",
        "base_url": "https://www.wamia.tn/sport-et-loisir.html",
        **MAGENTO,
        "compare_at_price_selector": "span.old-price, span.special-price",
        "stock_selector": "",
        "images_selector": "img.product-image-photo",
        "pagination_next_selector": "a.next",
        "category_name": "Sport & Loisirs",
    },
    {
        "name": "wamia_beaute_hygiene",
        "base_url": "https://www.wamia.tn/beaute-bien-etre.html",
        **MAGENTO,
        "compare_at_price_selector": "span.old-price, span.special-price",
        "stock_selector": "",
        "images_selector": "img.product-image-photo",
        "pagination_next_selector": "a.next",
        "category_name": "Beauté & Bien-être",
    },
    {
        "name": "wamia_jeux_jouets",
        "base_url": "https://www.wamia.tn/jeux-et-jouets.html",
        **MAGENTO,
        "compare_at_price_selector": "span.old-price, span.special-price",
        "stock_selector": "",
        "images_selector": "img.product-image-photo",
        "pagination_next_selector": "a.next",
        "category_name": "Jeux & Jouets",
    },
    {
        "name": "wamia_bricolage",
        "base_url": "https://www.wamia.tn/bricolage.html",
        **MAGENTO,
        "compare_at_price_selector": "span.old-price, span.special-price",
        "stock_selector": "",
        "images_selector": "img.product-image-photo",
        "pagination_next_selector": "a.next",
        "category_name": "Bricolage",
    },
    {
        "name": "wamia_auto_moto",
        "base_url": "https://www.wamia.tn/auto-moto.html",
        **MAGENTO,
        "compare_at_price_selector": "span.old-price, span.special-price",
        "stock_selector": "",
        "images_selector": "img.product-image-photo",
        "pagination_next_selector": "a.next",
        "category_name": "Auto & Moto",
    },
    {
        "name": "wamia_epicerie",
        "base_url": "https://www.wamia.tn/epicerie.html",
        **MAGENTO,
        "compare_at_price_selector": "span.old-price, span.special-price",
        "stock_selector": "",
        "images_selector": "img.product-image-photo",
        "pagination_next_selector": "a.next",
        "category_name": "Épicerie",
    },
    {
        "name": "wamia_jardin",
        "base_url": "https://www.wamia.tn/jardin.html",
        **MAGENTO,
        "compare_at_price_selector": "span.old-price, span.special-price",
        "stock_selector": "",
        "images_selector": "img.product-image-photo",
        "pagination_next_selector": "a.next",
        "category_name": "Jardin",
    },
    {
        "name": "wamia_animalerie",
        "base_url": "https://www.wamia.tn/animalerie.html",
        **MAGENTO,
        "compare_at_price_selector": "span.old-price, span.special-price",
        "stock_selector": "",
        "images_selector": "img.product-image-photo",
        "pagination_next_selector": "a.next",
        "category_name": "Animalerie",
    },
    # --- Noonclo: Shopify, JSON catalogue API -------------------------
    #
    # The shop exposes its whole catalogue through /products.json (90
    # products). Its collection pages (/collections/homme, /collections/soldes)
    # do NOT expose a products.json of their own, so every collection source
    # would return the very same 90 products and only the last one synced
    # would decide their category. One catalogue source is therefore the
    # honest representation, and each product is filed under its own Shopify
    # product type (Pantalons, Sacs, T-Shirts...).
    {
        "name": "noonclo_catalogue",
        "base_url": "https://noonclo.com/collections/all",
        **SHOPIFY,
        "price_selector": ".grid-product__price",
        "compare_at_price_selector": ".grid-product__price--original",
        "stock_selector": "",
        "images_selector": "img[data-src]",
        "pagination_next_selector": "link[rel=next]",
        "api_path": "/products.json",
        "category_name": "Mode",
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
            # Attach the storefront icon of the category this source feeds.
            category_name = defaults.get("category_name") or ""
            defaults["category_icon"] = icon_for(category_name)
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
