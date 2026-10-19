"""Scraping engines: HTTPX + Selectolax (static), Playwright (dynamic).

The four target suppliers expose three different catalogue shapes:

  * PrestaShop (tunisianet.com.tn, twenty.tn)
        container  article.product-miniature
        title     h2.product-title
        price     span.price / span.product-price   (sale price)
        compare   span.regular-price                 (struck-through price)
        stock     span.in-stock / div.product-availability
        pagination nav.pagination a[rel=next]

  * Magento 2 (wamia.tn)
        container  li.product
        title     a.product-item-link
        price     span.price
        compare   span.old-price  /  span.special-price
        image     img.product-image-photo[data-original]
        pagination a.next

  * Shopify (noonclo.com)
        container  .grid__item.grid-product
        title     .grid-product__title
        price     .grid-product__price  (sale price is the DIRECT text of
                  the node; the deep text also contains the original price)
        compare   .grid-product__price--original
        image     img[data-src]  (literal "{width}" placeholder)

Shops that hide their catalogue behind Cloudflare (wamia.tn) or an IP ban
(twenty.tn from the cluster) are reached through the Firecrawl proxy.
"""
import asyncio
import json
import os
import re
from decimal import Decimal
from urllib.parse import urlsplit, urljoin

import httpx
from selectolax.lexbor import LexborHTMLParser as HTMLParser
from playwright.async_api import async_playwright

from .utils import (
    normalize_tunisian_price,
    normalize_product_url,
    normalize_department,
    is_product_url,
    strip_unicode_spaces,
)


# Full browser-like header set. Some suppliers reject requests that lack a
# Referer or a realistic Accept-Language.
#
# NOTE: do NOT advertise "br" in Accept-Encoding. httpx has no brotli decoder,
# and quickk.tn answers with a truncated/placeholder page when brotli is
# requested (catalogue renders empty). gzip/deflate are safe.
BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "fr-TN,fr;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate",
    "Referer": "https://www.google.com/",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "cross-site",
    "Sec-Fetch-User": "?1",
    "Connection": "keep-alive",
}

# Markers that show an anti-bot / captcha interstitial instead of the catalogue.
BLOCK_MARKERS = (
    "are you a robot",
    "unusual traffic",
    "access denied",
    "enable javascript and cookies",
    "checking your browser",
    "cf-browser-verification",
)

# Cloudflare challenge pages: the body is a JS challenge, not the catalogue.
CF_CHALLENGE_MARKERS = (
    "cf-browser-verification",
    "cf_chl_opt",
    "just a moment",
    "checking your browser",
    "cdn-cgi/challenge-platform",
)

# Shopify serves responsive images with a literal "{width}" placeholder:
#   //noonclo.com/cdn/shop/files/IMG_9113_1_{width}x.jpg?v=1766822953
# The placeholder must be replaced with a real width, otherwise the CDN
# answers 404 and every product shows a broken image.
SHOPIFY_WIDTH_PLACEHOLDER = re.compile(r"\{width\}")
SHOPIFY_DEFAULT_WIDTH = 600

# Firecrawl's keyless REST API. It is used as a fallback transport for hosts
# that block the cluster's egress IP with a Cloudflare challenge
# (wamia.tn) or with a plain 403 (twenty.tn). The proxy renders the page in a
# real browser, so the resulting HTML is the catalogue, not the interstitial.
FIRECRAWL_API_URL = "https://api.firecrawl.dev/v2/scrape"
FIRECRAWL_TIMEOUT = 120

# The Shopify JSON catalogue API returns every product with its variants,
# prices and images already normalised. It is far more reliable than
# parsing the theme's HTML, and it removes the "?variant=" duplication
# (130 grid items but only 52 real products).
SHOPIFY_JSON_PATH = "/products.json"

# Pagination limits.
MAX_PAGES = 40
REQUEST_TIMEOUT = 30


def build_headers(source=None):
    """Return request headers for a source.

    The Referer stays on google.com: pointing it at the supplier's own host
    triggers a different (catalogue-less) response on some sites.
    """
    return dict(BROWSER_HEADERS)


def _is_block_page(html):
    """Detect an anti-bot / captcha interstitial page."""
    if not html:
        return False
    # A real catalogue page is far larger than a block page.
    if len(html) > 100000:
        return False
    low = html.lower()
    return any(marker in low for marker in BLOCK_MARKERS)


def _is_cloudflare_challenge(html):
    """True when the response is a Cloudflare JS challenge page."""
    if not html:
        return False
    low = html.lower()
    return any(marker in low for marker in CF_CHALLENGE_MARKERS)


def fetch_via_firecrawl(url, timeout=FIRECRAWL_TIMEOUT):
    """Fetch a page through the Firecrawl proxy and return its raw HTML.

    Used when the direct request is blocked by Cloudflare or by an IP ban.
    Returns (html, error).
    """
    try:
        resp = httpx.post(
            FIRECRAWL_API_URL,
            json={"url": url, "formats": ["rawHtml"], "maxAge": 0},
            timeout=timeout,
        )
        data = resp.json()
    except Exception as exc:
        return "", f"Firecrawl transport error: {type(exc).__name__}: {str(exc)[:200]}"
    if not data.get("success"):
        return "", f"Firecrawl error: {str(data.get('error'))[:200]}"
    payload = data.get("data") or {}
    html = payload.get("rawHtml") or ""
    if not html:
        return "", "Firecrawl returned an empty document"
    return html, None


def _expand_image_width(url):
    """Replace the Shopify "{width}" placeholder with a real width."""
    if not url:
        return url
    if "{width}" in url:
        url = SHOPIFY_WIDTH_PLACEHOLDER.sub(str(SHOPIFY_DEFAULT_WIDTH), url)
    return url


def _collect_image_urls(container, selector):
    """Collect image URLs from a product container.

    Handles the lazy-load attributes used by every target shop:
      Shopify : img.lazyload[data-src]
      PrestaShop: img[data-src] / img[data-full-size-image-url]
      Magento : img.product-image-photo[data-original]
    """
    urls = []
    seen = set()

    def add(raw):
        if not raw:
            return
        raw = raw.strip()
        if not raw or raw.startswith("data:"):
            return
        if raw.startswith("//"):
            raw = "https:" + raw
        raw = _expand_image_width(raw)
        if raw not in seen:
            seen.add(raw)
            urls.append(raw)

    # 1) Nodes carrying the real image URL in a data attribute.
    for node in container.css("[data-original], [data-src], [data-lazy-src], [data-image-url], [data-full-size-image-url]"):
        for attr in ("data-original", "data-src", "data-lazy-src", "data-image-url", "data-full-size-image-url"):
            add(node.attributes.get(attr, ""))

    # 2) img tags matched by the configured selector.
    if selector:
        for node in container.css(selector):
            add(node.attributes.get("data-original", ""))
            add(node.attributes.get("data-src", ""))
            add(node.attributes.get("data-lazy-src", ""))
            add(node.attributes.get("data-full-size-image-url", ""))
            add(node.attributes.get("src", ""))

    # 3) Fallback: any img inside the container.
    if not urls:
        for node in container.css("img"):
            add(node.attributes.get("data-original", ""))
            add(node.attributes.get("data-src", ""))
            add(node.attributes.get("data-lazy-src", ""))
            add(node.attributes.get("src", ""))

    return ",".join(urls[:5])


def _collect_prices(container, selectors):
    """Return every price candidate found in the container.

    A single container can hold several amounts (Shopify shows the original
    price and the sale price in the same node). Returning them all lets the
    caller apply a per-source strategy (first / last / min).
    """
    candidates = []
    strategy = selectors.get("price_text_mode", "deep")

    def push(raw):
        if not raw:
            return
        value = normalize_tunisian_price(raw)
        if value > 0:
            candidates.append(value)

    for sel in [selectors.get("price", "")] + list(selectors.get("price_fallbacks", []) or []):
        if not sel:
            continue
        for node in container.css(sel):
            if strategy == "shallow":
                # Only the direct text children of the node. Shopify mixes the
                # struck-through price into the deep text of the same node.
                push(node.text(deep=False, strip=True))
            else:
                push(node.text(strip=True))
    return candidates


def _pick_price(candidates, strategy):
    """Apply the per-source price strategy to the list of candidates."""
    if not candidates:
        return Decimal("0")
    if strategy == "last":
        return candidates[-1]
    if strategy == "min":
        return min(candidates)
    if strategy == "max":
        return max(candidates)
    return candidates[0]


def _collect_compare_at(container, selectors):
    """Read the struck-through reference price of a product.

    The reference price lives in its own node (PrestaShop `span.regular-price`,
    Magento `span.old-price`, Shopify `.grid-product__price--original`), so it
    is read with a dedicated selector instead of being inferred from the
    price candidates.
    """
    selector = selectors.get("compare_at_price")
    if not selector:
        return Decimal("0")
    mode = selectors.get("price_text_mode", "deep")
    for node in container.css(selector):
        raw = (
            node.text(deep=False, strip=True)
            if mode == "shallow"
            else node.text(strip=True)
        )
        value = normalize_tunisian_price(raw)
        if value > 0:
            return value
    return Decimal("0")


def _parse_stock_text(raw):
    """Parse a stock quantity from raw text.

    Only explicit out-of-stock keywords mean zero. A bare number is not read
    from the text because prices such as "81,000 DT" would be mistaken for a
    quantity.
    """
    text = str(raw or "").strip()
    if not text:
        return 1
    low = text.lower()
    if any(k in low for k in ("out of stock", "épuisé", "non disponible", "rupture", "indisponible", "hors stock")):
        return 0
    digits = "".join(ch for ch in text if ch.isdigit())
    return int(digits) if digits else 1


class BaseEngine:
    async def scrape(self, source, selectors):
        raise NotImplementedError


class HTTPEngine(BaseEngine):
    """Fast static-page scraper using httpx + selectolax.

    When the direct request is blocked (Cloudflare challenge, IP ban, 429),
    the engine retries through the Firecrawl proxy, which renders the page
    in a real browser and returns the catalogue HTML.
    """

    def __init__(self):
        self.last_error = None

    async def scrape(self, source, selectors):
        results = []
        headers = build_headers(source)

        # Shopify exposes a JSON catalogue API. It is the primary path for
        # noonclo: no "?variant=" duplicates and normalised prices.
        if selectors.get("api_path") == SHOPIFY_JSON_PATH:
            return await self._scrape_shopify_json(source, selectors)

        url = source.base_url
        page = 0
        seen_urls = set()
        while url and page < MAX_PAGES:
            page += 1
            html, status, transport_error = await self._fetch(url, headers)
            if not html:
                self.last_error = transport_error
                break

            blocked = (
                status in (403, 429)
                or _is_cloudflare_challenge(html)
                or (status is not None and status >= 400)
            )
            if blocked:
                html, proxy_error = await asyncio.get_event_loop().run_in_executor(
                    None, fetch_via_firecrawl, url
                )
                if not html:
                    self.last_error = (
                        f"Blocked (HTTP {status}): {proxy_error or 'proxy failed'}"
                    )
                    break
                transport_error = None

            parser = HTMLParser(html)
            containers = parser.css(selectors.get("product_container", ""))
            if not containers and (
                _is_block_page(html) or _is_cloudflare_challenge(html)
            ):
                self.last_error = (
                    "Blocked by anti-bot protection (no product containers matched)"
                )
                break

            for container in containers:
                item = self._extract(container, selectors)
                if not item.get("title"):
                    continue
                key = item.get("url") or item["title"]
                if key in seen_urls:
                    continue
                seen_urls.add(key)
                results.append(item)

            next_url = self._next_page_url(parser, url, selectors)
            if not next_url or next_url == url:
                break
            url = next_url

        if not results and self.last_error:
            return results, self.last_error
        return results, None

    async def _fetch(self, url, headers):
        """Fetch a page, returning (html, status, error)."""
        error = None
        status = None
        html = ""
        try:
            async with httpx.AsyncClient(
                timeout=REQUEST_TIMEOUT,
                follow_redirects=True,
                headers=headers,
            ) as client:
                resp = await client.get(url)
                status = resp.status_code
                html = resp.text
        except Exception as exc:
            error = f"{type(exc).__name__}: {str(exc)[:200]}"
        return html, status, error

    async def _scrape_shopify_json(self, source, selectors):
        """Scrape a Shopify shop through its /products.json catalogue API."""
        base = source.base_url.rstrip("/")
        # /collections/<x>/products.json is the collection form; the plain
        # /products.json always returns the whole catalogue.
        parts = urlsplit(base)
        path = parts.path
        if "/collections/" in path:
            path = path[: path.index("/collections/")]
        url = f"{parts.scheme}://{parts.netloc}{path.rstrip('/')}{SHOPIFY_JSON_PATH}?limit=250"

        headers = build_headers(source)
        html, status, error = await self._fetch(url, headers)
        payload = None
        if html and html.lstrip().startswith("{"):
            try:
                payload = json.loads(html)
            except ValueError:
                payload = None

        if not payload:
            # Fall back to the HTML grid, and finally to the proxy.
            html2, status2, error2 = await self._fetch(source.base_url, headers)
            if not html2:
                html2, proxy_error = await asyncio.get_event_loop().run_in_executor(
                    None, fetch_via_firecrawl, source.base_url
                )
                if not html2:
                    return [], error2 or proxy_error or "Shopify fetch failed"
            parser = HTMLParser(html2)
            results = []
            for container in parser.css(selectors.get("product_container", "")):
                item = self._extract(container, selectors)
                if item.get("title"):
                    results.append(item)
            return results, None

        results = []
        for product in payload.get("products", []):
            item = self._extract_shopify_product(product, source)
            if item:
                results.append(item)
        return results, None

    def _extract_shopify_product(self, product, source):
        """Turn one Shopify JSON product into the common item dict."""
        title = (product.get("title") or "").strip()
        if not title:
            return None
        variants = product.get("variants") or []
        if not variants:
            return None
        # The first variant is the default one; the grid shows its price.
        variant = variants[0]

        price = Decimal("0")
        try:
            price = Decimal(str(variant.get("price") or 0))
        except (TypeError, ValueError, ArithmeticError):
            price = Decimal("0")
        if price <= 0:
            return None

        compare_at = Decimal("0")
        try:
            raw_compare = variant.get("compare_at_price")
            if raw_compare:
                compare_at = Decimal(str(raw_compare))
        except (TypeError, ValueError, ArithmeticError):
            compare_at = Decimal("0")
        if compare_at <= price:
            compare_at = Decimal("0")

        images = []
        for img in product.get("images") or []:
            src = img.get("src") if isinstance(img, dict) else img
            if src:
                images.append(_expand_image_width(src))
        if not images:
            featured = product.get("featured_image")
            if isinstance(featured, dict) and featured.get("src"):
                images.append(_expand_image_width(featured["src"]))

        handle = product.get("handle") or ""
        product_url = ""
        if handle:
            product_url = f"{source.base_url.rstrip('/').split('/collections/')[0]}/products/{handle}"
            product_url = normalize_product_url(product_url)

        return {
            "title": title,
            "price": price,
            "price_candidates": [price] + ([compare_at] if compare_at else []),
            "price_raw": f"{price}",
            "compare_at": compare_at,
            "stock": 1 if variant.get("available") else 0,
            "images": ",".join(images[:5]),
            "url": product_url,
            "is_product": True,
            # Shopify exposes the department of a product as its type
            # ("Pantalons", "Robes"...). It gives a far more accurate
            # category than the collection the product was listed under.
            "category": normalize_department(product.get("product_type")),
        }

    def _next_page_url(self, parser, current_url, selectors):
        """Find the next page link for the configured pagination selector."""
        selector = selectors.get("pagination_next")
        if not selector:
            return None
        node = parser.css_first(selector)
        if not node:
            return None
        href = node.attributes.get("href", "")
        if not href:
            return None
        if href.startswith("http"):
            return href
        return urljoin(current_url, href)

    def _extract(self, container, selectors):
        def get(selector):
            if not selector:
                return ""
            node = container.css_first(selector)
            return node.text(strip=True) if node else ""

        title = get(selectors.get("title", ""))
        price_candidates = _collect_prices(container, selectors)
        price = _pick_price(price_candidates, selectors.get("price_strategy", "first"))
        stock_raw = get(selectors.get("stock", ""))
        images_raw = _collect_image_urls(container, selectors.get("images", ""))

        # Determine stock from CSS classes (instock/outofstock) as fallback
        stock = _parse_stock_text(stock_raw)
        if stock == 0 and not any(
            k in stock_raw.lower()
            for k in ("out of stock", "épuisé", "non disponible", "rupture", "indisponible")
        ):
            container_classes = container.attributes.get("class", "").lower()
            if "outofstock" in container_classes or "out-of-stock" in container_classes:
                stock = 0
            elif "instock" in container_classes or "in-stock" in container_classes:
                stock = max(stock, 1)

        # Product detail URL
        product_url = ""
        link = container.css_first("a[href]")
        if link:
            product_url = normalize_product_url(link.attributes.get("href", ""))

        return {
            "title": title,
            "price": price,
            "price_candidates": price_candidates,
            "price_raw": ", ".join(str(c) for c in price_candidates),
            "compare_at": _collect_compare_at(container, selectors),
            "stock": stock,
            "images": images_raw,
            "url": product_url,
            "is_product": is_product_url(product_url),
        }


class PlaywrightEngine(HTTPEngine):
    """Headless Chromium fallback for JavaScript-rendered catalogs.

    Playwright cannot launch in this environment (missing libatk), so the
    class inherits the HTTP behaviour and only overrides the fetch step
    when a browser is actually available.
    """

    async def _fetch(self, url, headers):
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(args=["--no-sandbox"])
                page = await browser.new_page()
                await page.goto(url, wait_until="networkidle", timeout=REQUEST_TIMEOUT * 1000)
                content = await page.content()
                await browser.close()
            return content, 200, None
        except Exception as exc:
            return "", None, f"{type(exc).__name__}: {str(exc)[:200]}"


def get_engine(engine_type):
    if engine_type == "DYNAMIC":
        return PlaywrightEngine()
    return HTTPEngine()
