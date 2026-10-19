"""Scraping engines: HTTPX + Selectolax (static), Playwright (dynamic)."""
import asyncio
from decimal import Decimal
import httpx
from selectolax.lexbor import LexborHTMLParser as HTMLParser
from playwright.async_api import async_playwright

from .utils import normalize_tunisian_price, normalize_product_url, is_product_url


# Full browser-like header set. Some suppliers (quickk.tn) reject requests
# that lack a Referer or a realistic Accept-Language.
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


class BaseEngine:
    async def scrape(self, source, selectors):
        raise NotImplementedError


class HTTPEngine(BaseEngine):
    """Fast static-page scraper using httpx + selectolax."""

    async def scrape(self, source, selectors):
        results = []
        headers = build_headers(source)
        async with httpx.AsyncClient(timeout=30, follow_redirects=True, headers=headers) as client:
            try:
                resp = await client.get(source.base_url)
                resp.raise_for_status()
            except Exception as exc:
                return results, str(exc)

        parser = HTMLParser(resp.text)
        containers = parser.css(selectors.get("product_container", ""))
        if not containers and _is_block_page(resp.text):
            return results, "Blocked by anti-bot protection (no product containers matched)"
        for container in containers:
            item = self._extract(container, selectors)
            if item.get("title"):
                results.append(item)
        return results, None

    def _extract(self, container, selectors):
        def get(selector):
            if not selector:
                return ""
            node = container.css_first(selector)
            return node.text(strip=True) if node else ""

        def get_attr(selector, attr):
            if not selector:
                return ""
            node = container.css_first(selector)
            return node.attributes.get(attr, "") if node else ""

        def get_images(selector):
            """Collect all image URLs, preferring lazy-load attributes over src.

            Handles: data-src, data-lazy-src, data-image-url, src.
            Skips data: URIs (inline placeholders).
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
                if raw not in seen:
                    seen.add(raw)
                    urls.append(raw)

            # 1) Slider elements carrying the real image URL
            for node in container.css("[data-image-url]"):
                add(node.attributes.get("data-image-url", ""))

            # 2) img tags matched by selector
            if selector:
                for node in container.css(selector):
                    add(node.attributes.get("data-src", ""))
                    add(node.attributes.get("data-lazy-src", ""))
                    add(node.attributes.get("data-image-url", ""))
                    add(node.attributes.get("src", ""))

            # 3) Fallback: any img inside the container
            if not urls:
                for node in container.css("img"):
                    add(node.attributes.get("data-src", ""))
                    add(node.attributes.get("data-lazy-src", ""))
                    add(node.attributes.get("src", ""))

            return ",".join(urls)

        title = get(selectors.get("title", ""))
        price_raw = get(selectors.get("price", ""))
        # Fallback price selectors: some layouts rename or re-render the node.
        if not price_raw:
            for alt in selectors.get("price_fallbacks", []) or []:
                candidate = get(alt)
                if candidate:
                    price_raw = candidate
                    break
        stock_raw = get(selectors.get("stock", ""))
        images_raw = get_images(selectors.get("images", ""))

        # Determine stock from CSS classes (instock/outofstock) as fallback
        stock = self._parse_stock(stock_raw)
        if stock == 0 and not any(k in stock_raw.lower() for k in ["out of stock", "épuisé", "non disponible", "rupture", "indisponible"]):
            container_classes = container.attributes.get("class", "").lower()
            if "outofstock" in container_classes:
                stock = 0
            elif "instock" in container_classes:
                stock = max(stock, 1)

        # Product detail URL
        product_url = ""
        link = container.css_first("a[href]")
        if link:
            product_url = normalize_product_url(link.attributes.get("href", ""))

        return {
            "title": title,
            "price": normalize_tunisian_price(price_raw),
            "price_raw": price_raw,
            "stock": stock,
            "images": images_raw,
            "url": product_url,
            "is_product": is_product_url(product_url),
        }

    @staticmethod
    def _parse_stock(raw):
        """Parse stock quantity from raw text.

        Avoids matching '0' inside prices like '81,000 DT'.
        Only treats explicit out-of-stock keywords as zero stock.
        """
        text = str(raw).strip()
        if not text:
            return 1
        text_lower = text.lower()
        if any(k in text_lower for k in ["out of stock", "épuisé", "non disponible", "rupture", "indisponible"]):
            return 0
        # Extract the first meaningful number (not part of a price)
        digits = "".join(ch for ch in text if ch.isdigit())
        return int(digits) if digits else 1

    def _extract_brand(self, container, selectors):
        """Extract brand from product container using selectors or heuristics."""
        brand_sel = selectors.get("brand", "")
        if brand_sel:
            node = container.css_first(brand_sel)
            if node:
                return node.text(strip=True)
        # Heuristic: look for common brand indicators
        for sel in ["[class*='brand']", "[class*='vendor']", ".brand", ".vendor"]:
            node = container.css_first(sel)
            if node:
                return node.text(strip=True)
        return ""

    def _extract_model(self, container, selectors):
        """Extract model from product container."""
        model_sel = selectors.get("model", "")
        if model_sel:
            node = container.css_first(model_sel)
            if node:
                return node.text(strip=True)
        return ""

    def _extract_category(self, container, selectors):
        """Extract category from product container."""
        cat_sel = selectors.get("category", "")
        if cat_sel:
            node = container.css_first(cat_sel)
            if node:
                return node.text(strip=True)
        return ""


class PlaywrightEngine(BaseEngine):
    """Headless Chromium fallback for JavaScript-rendered catalogs."""

    async def scrape(self, source, selectors):
        results = []
        error = None
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(args=["--no-sandbox"])
                page = await browser.new_page()
                await page.goto(source.base_url, wait_until="networkidle", timeout=30000)
                content = await page.content()
                await browser.close()
        except Exception as exc:
            error = str(exc)
            return results, error

        parser = HTMLParser(content)
        containers = parser.css(selectors.get("product_container", ""))
        for container in containers:
            item = self._extract(container, selectors)
            if item.get("title"):
                results.append(item)
        return results, None

    def _extract(self, container, selectors):
        def get(selector):
            if not selector:
                return ""
            node = container.css_first(selector)
            return node.text(strip=True) if node else ""

        def get_attr(selector, attr):
            if not selector:
                return ""
            node = container.css_first(selector)
            return node.attributes.get(attr, "") if node else ""

        def get_images(selector):
            """Collect all image URLs, preferring lazy-load attributes over src.

            Handles: data-src, data-lazy-src, data-image-url, src.
            Skips data: URIs (inline placeholders).
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
                if raw not in seen:
                    seen.add(raw)
                    urls.append(raw)

            # 1) Slider elements carrying the real image URL
            for node in container.css("[data-image-url]"):
                add(node.attributes.get("data-image-url", ""))

            # 2) img tags matched by selector
            if selector:
                for node in container.css(selector):
                    add(node.attributes.get("data-src", ""))
                    add(node.attributes.get("data-lazy-src", ""))
                    add(node.attributes.get("data-image-url", ""))
                    add(node.attributes.get("src", ""))

            # 3) Fallback: any img inside the container
            if not urls:
                for node in container.css("img"):
                    add(node.attributes.get("data-src", ""))
                    add(node.attributes.get("data-lazy-src", ""))
                    add(node.attributes.get("src", ""))

            return ",".join(urls)

        title = get(selectors.get("title", ""))
        price_raw = get(selectors.get("price", ""))
        # Fallback price selectors: some layouts rename or re-render the node.
        if not price_raw:
            for alt in selectors.get("price_fallbacks", []) or []:
                candidate = get(alt)
                if candidate:
                    price_raw = candidate
                    break
        stock_raw = get(selectors.get("stock", ""))
        images_raw = get_images(selectors.get("images", ""))

        # Determine stock from CSS classes (instock/outofstock) as fallback
        stock = self._parse_stock(stock_raw)
        if stock == 0 and not any(k in stock_raw.lower() for k in ["out of stock", "épuisé", "non disponible", "rupture", "indisponible"]):
            container_classes = container.attributes.get("class", "").lower()
            if "outofstock" in container_classes:
                stock = 0
            elif "instock" in container_classes:
                stock = max(stock, 1)

        product_url = ""
        link = container.css_first("a[href]")
        if link:
            product_url = normalize_product_url(link.attributes.get("href", ""))

        return {
            "title": title,
            "price": normalize_tunisian_price(price_raw),
            "price_raw": price_raw,
            "stock": stock,
            "images": images_raw,
            "url": product_url,
            "is_product": is_product_url(product_url),
        }

    @staticmethod
    def _parse_stock(raw):
        """Parse stock quantity from raw text.

        Avoids matching '0' inside prices like '81,000 DT'.
        Only treats explicit out-of-stock keywords as zero stock.
        """
        text = str(raw).strip()
        if not text:
            return 1
        text_lower = text.lower()
        if any(k in text_lower for k in ["out of stock", "épuisé", "non disponible", "rupture", "indisponible"]):
            return 0
        # Extract the first meaningful number (not part of a price)
        digits = "".join(ch for ch in text if ch.isdigit())
        return int(digits) if digits else 1


def get_engine(engine_type):
    if engine_type == "DYNAMIC":
        return PlaywrightEngine()
    return HTTPEngine()
