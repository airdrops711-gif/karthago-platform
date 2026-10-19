"""Currency and text normalizers for Tunisian prices."""
import re
from decimal import Decimal, InvalidOperation
from urllib.parse import urlsplit


# Zero-width / non-breaking spaces used as thousands separators by French and
# Arabic storefronts. U+202F (narrow no-break space) is what PrestaShop emits
# between the thousands and the decimal part ("1<NBSP>169,000 DT"), and it is
# NOT removed by str.replace(" ", "") because it is a different codepoint.
# Leaving it in the digit string makes Decimal() raise InvalidOperation and
# the whole price silently collapses to 0.
UNICODE_SPACES = (
    "\u00a0"  # no-break space
    "\u202f"  # narrow no-break space
    "\u2007"  # figure space
    "\u2009"  # thin space
    "\u2028"  # line separator
    "\u2029"  # paragraph separator
    "\ufeff"  # zero width no-break space
    "\u200b"  # zero width space
)


def strip_unicode_spaces(text):
    """Remove every exotic space codepoint plus regular spaces."""
    if not text:
        return text
    for sp in UNICODE_SPACES:
        text = text.replace(sp, " ")
    return text.replace(" ", "")


TND_PATTERNS = [
    re.compile(r"([\d\s\.,]+)\s*(?:DT|TND|د\.ت)", re.IGNORECASE),
    re.compile(r"(?:DT|TND|د\.ت)\s*([\d\s\.,]+)", re.IGNORECASE),
    re.compile(r"([\d\s\.,]+)"),
]

# Currency symbols that prefix or suffix a bare amount.
CURRENCY_SYMBOLS = ("$", "€", "£", "¥", "₹", "ر.س", "ج.م")

# Words that may sit between the currency marker and the number,
# e.g. "Price Now $39.99 Was $52.00" -> we want the first amount.
PRICE_NOISE_WORDS = (
    r"(?:price|now|was|from|to|only|just|save|off|deal|was|est|سعر|prix)"
)


def _strip_price_noise(text):
    """Reduce a price label to its first bare amount.

    "Price Now $39.99 Was $52.00" -> "39.99"
    "Price $84.28" -> "84.28"
    "84,000 DT" -> "84,000 DT"
    """
    # Prefer an amount immediately attached to a currency symbol.
    symbol_re = "(?:" + "|".join(re.escape(s) for s in CURRENCY_SYMBOLS) + ")"
    match = re.search(
        rf"{symbol_re}\s*(\d[\d\s\.,]*)", text
    ) or re.search(
        rf"(\d[\d\s\.,]*)\s*{symbol_re}", text
    )
    if match:
        return match.group(1).strip()

    # Otherwise drop leading noise words and keep the first amount.
    cleaned = re.sub(
        rf"^[\s\.,]*(?:{PRICE_NOISE_WORDS})[\s\.,:]*", "", text, flags=re.IGNORECASE
    )
    match = re.search(r"(\d[\d\s\.,]*)", cleaned)
    if match:
        return match.group(1).strip()
    return text


def normalize_tunisian_price(raw):
    """Normalize unstructured Tunisian price strings into Decimal (3 decimals).

    Handles: "149,000 DT", "149.000 TND", "149 DT", "149,000 د.ت", "$84.28"

    Tunisian convention: comma is decimal separator, dot is thousand separator.
    However, both "149,000 DT" and "149.000 TND" should normalize to 149.000.
    """
    if raw is None:
        return Decimal("0.000")
    # Normalise exotic spaces BEFORE any parsing so that "1<NBSP>169,000 DT"
    # is seen as "1169000 DT" and not as a number with a stray separator.
    text = strip_unicode_spaces(str(raw)).strip()
    if not text:
        return Decimal("0.000")

    # Drop label noise ("Price", "Now", "Was") and keep the first amount.
    text = _strip_price_noise(text)
    if not text:
        return Decimal("0.000")

    for pattern in TND_PATTERNS:
        match = pattern.search(text)
        if match:
            number_str = strip_unicode_spaces(match.group(1))
            if not number_str:
                continue

            has_dot = "." in number_str
            has_comma = "," in number_str

            if has_dot and has_comma:
                # Both separators: last one is decimal, other is thousand
                last_dot = number_str.rfind(".")
                last_comma = number_str.rfind(",")
                if last_dot > last_comma:
                    # Dot is decimal, comma is thousand
                    number_str = number_str.replace(",", "").replace(".", ".")
                else:
                    # Comma is decimal, dot is thousand
                    number_str = number_str.replace(".", "").replace(",", ".")
            elif has_comma:
                # Only comma: treat as decimal separator
                number_str = number_str.replace(",", ".")
            elif has_dot:
                # Only dot: treat as decimal separator (e.g., "149.000 TND")
                number_str = number_str.replace(".", ".")
            else:
                number_str = number_str

            try:
                return Decimal(number_str).quantize(Decimal("0.001"))
            except (InvalidOperation, ValueError):
                continue
    return Decimal("0.000")


# Query parameters that change on every request (tracking / session ids).
# They must be stripped or the same product is re-created on each scrape.
TRACKING_QUERY_KEYS = {
    "algo_pvid",
    "algo_exp_id",
    "algo_expid",
    "algo_chname",
    "spm",
    "pvid",
    "algo_source",
    "gatewayAdapt",
    "sk",
    "trk",
    "trkCampaign",
    "scm",
    "thouid",
    "btsid",
    "ws_ab_test",
    "storeName",
    "curPageLogUid",
    "pdp_ext_f",
    "pdp_ext_s",
    "pdp_npi",
    "pdp_f_fs",
    "utparam-url",
    "utparam_platform",
    "utparam_campaign",
    "search_p4p_id",
    "spm-premium",
    "aem_p4p_detail",
    "aem_added_pdp_info",
    "gatewayAdapt",
    "spm-premium",
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "gclid",
    "fbclid",
}

# Substrings that mark a query parameter as volatile/session-bound.
TRACKING_QUERY_MARKERS = (
    "loguid",
    "logid",
    "session",
    "timestamp",
    "_ts",
    "rand",
    "token",
)


# URL path fragments that are NOT product detail pages.
NON_PRODUCT_PATH_MARKERS = (
    "/ssr/",
    "/bundle",
    "/bundle-deal",
    "/coupon",
    "/category",
    "/wholesale",
    "/search",
    "/shop",
    "/cart",
    "/login",
    "/register",
    "/help",
    "/impress",
    "/about",
)

# Path fragments that identify a product detail page.
PRODUCT_PATH_MARKERS = (
    "/item/",
    "/product/",
    "/produit/",
    "/produits/",
    "/p/",
    "/dp/",
)

# PrestaShop (tunisianet, twenty) and Magento (wamia) end every product
# detail URL with ".html" while their category URLs never do:
#   category: https://www.tunisianet.com.tn/301-pc-portable-tunisie
#   product : https://www.tunisianet.com.tn/pc-portable-tunisie/98008-pc-....html
# The ".html" suffix is therefore the most reliable product signal.
PRODUCT_URL_SUFFIX = ".html"

# Category landing pages of the PrestaShop shops: "/<id>-<slug>" with no
# product id and no ".html" suffix.
_CATEGORY_ONLY_PATH = re.compile(r"^/\d+-[a-z0-9\-]*$")


def is_product_url(url):
    """True when the URL looks like a product detail page.

    Filters out AliExpress SSR/bundle-deal and category landing pages that are
    picked up by the generic "first link in the container" heuristic.
    """
    if not url:
        return False
    low = url.lower()
    if any(marker in low for marker in PRODUCT_PATH_MARKERS):
        return True
    path = urlsplit(low).path
    # A ".html" URL that is not a category landing page is a product page.
    if path.endswith(PRODUCT_URL_SUFFIX) and not _CATEGORY_ONLY_PATH.match(path):
        return True
    if any(marker in low for marker in NON_PRODUCT_PATH_MARKERS):
        return False
    # "/<id>-<slug>" is a category page on the PrestaShop shops.
    if _CATEGORY_ONLY_PATH.match(path):
        return False
    return True


def _is_tracking_key(key):
    """True when a query key is a tracking / session-bound parameter."""
    low = key.lower()
    if low in TRACKING_QUERY_KEYS:
        return True
    return any(marker in low for marker in TRACKING_QUERY_MARKERS)


# --------------------------------------------------------------------------
# Department names published by the suppliers.
#
# A supplier labels a product with its own wording ("Pantalons", "Sweat à
# capuche", "Cargo pants"). The storefront needs one clean name per
# department, otherwise the catalogue ends up with a dozen categories holding
# a single product each.
# --------------------------------------------------------------------------
DEPARTMENT_ALIASES = {
    # Clothing
    "pantalons": "Pantalons",
    "cargo pants": "Pantalons",
    "jogging": "Pantalons",
    "leggings": "Pantalons",
    "jupe": "Jupes",
    "ensemble": "Ensembles",
    "robes": "Robes",
    "robe": "Robes",
    "t-shirts": "T-Shirts",
    "t-shirt": "T-Shirts",
    "tshirt": "T-Shirts",
    "shirt": "Chemises",
    "shirts": "Chemises",
    "chemise": "Chemises",
    "chemises": "Chemises",
    "polo": "Polos",
    "polos": "Polos",
    "sweat à capuche": "Sweats",
    "sweat a capuche": "Sweats",
    "sweatshirt": "Sweats",
    "sweats": "Sweats",
    "manteau": "Manteaux",
    "manteaux": "Manteaux",
    "veste": "Vestes",
    "vestes": "Vestes",
    "active wear": "Sportswear",
    "activewear": "Sportswear",
    "chaussures": "Chaussures",
    "sacs": "Sacs",
    "bijoux": "Bijoux",
    "bijoux femme": "Bijoux",
    "accessoires de mode": "Accessoires Mode",
    "chaussure": "Chaussures",
    "sac": "Sacs",
    # Home
    "maison": "Maison",
    "maison & bureau": "Maison",
    "décoration": "Décoration",
    "deco": "Décoration",
    "literie": "Literie",
    "linge de maison": "Literie",
    "cuisine": "Cuisine",
    "vaisselle": "Cuisine",
    "rangement": "Rangement",
    "éclairage": "Éclairage",
    "eclairage": "Éclairage",
    "mobilier": "Mobilier",
    # Electronics
    "informatique": "Informatique",
    "ordinateur": "Informatique",
    "ordinateurs": "Informatique",
    "accessoires": "Accessoires",
    "câbles": "Câbles & Adaptateurs",
    "cables": "Câbles & Adaptateurs",
    "adaptateurs": "Câbles & Adaptateurs",
    "électroménager": "Électroménager",
    "electromenager": "Électroménager",
    "téléphones": "Téléphones",
    "telephones": "Téléphones",
    "smartphones": "Smartphones",
    "smartphone": "Smartphones",
    "tv": "TV & Audio",
    "audio": "TV & Audio",
    "photo": "Photo & Caméras",
    # Fashion accessories / misc
    "bijoux & accessoires": "Bijoux",
    "parfums": "Parfums",
    "beauté": "Beauté",
    "beaute": "Beauté",
    "sport": "Sport",
    "sports": "Sport",
    "enfants": "Enfants",
    "jouets": "Jouets",
    "jeux": "Jouets",
}

# Product types that are not real departments.
_IGNORED_DEPARTMENTS = {"", "free_gift", "gift", "default", "none"}


def normalize_department(raw, max_length=100):
    """Map a supplier department label to a clean storefront category name.

    Returns an empty string when the label is not a usable department, so
    the caller can fall back to the source-level category.
    """
    if not raw:
        return ""
    text = str(raw).strip()
    if not text or text.lower() in _IGNORED_DEPARTMENTS:
        return ""
    if text in DEPARTMENT_ALIASES.values():
        return text[:max_length]
    key = text.lower().strip()
    if key in DEPARTMENT_ALIASES:
        return DEPARTMENT_ALIASES[key][:max_length]
    # Unknown label: keep the supplier wording but title-case it so the
    # storefront stays consistent.
    cleaned = " ".join(word.capitalize() for word in text.split())
    return cleaned[:max_length]


def normalize_product_url(raw, max_length=500):
    """Normalize a supplier product URL into a stable, deduplication-safe form.

    - Expands protocol-relative "//host/path" to "https://host/path".
    - Drops tracking query parameters that change on every page load.
    - Sorts the remaining query parameters for a stable key.
    - Truncates to `max_length` so it fits the DB column.
    """
    if not raw:
        return ""
    url = str(raw).strip()
    if not url:
        return ""
    if url.startswith("//"):
        url = "https:" + url
    if not url.startswith(("http://", "https://")):
        return url[:max_length]

    try:
        from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

        parts = urlsplit(url)
        query = [
            (k, v)
            for k, v in parse_qsl(parts.query, keep_blank_values=True)
            if not _is_tracking_key(k)
        ]
        query.sort()
        cleaned = urlunsplit(
            (
                parts.scheme,
                parts.netloc,
                parts.path,
                urlencode(query),
                "",
            )
        )
        return cleaned[:max_length]
    except Exception:
        return url[:max_length]
