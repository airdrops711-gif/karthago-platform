"""Scraping engines: HTTPX + Selectolax (static), Playwright (dynamic)."""
import asyncio
from decimal import Decimal
import httpx
from selectolax.lexbor import LexborHTMLParser as HTMLParser
from playwright.async_api import async_playwright

from .utils import normalize_tunisian_price


class BaseEngine:
    async def scrape(self, source, selectors):
        raise NotImplementedError


class HTTPEngine(BaseEngine):
    """Fast static-page scraper using httpx + selectolax."""

    async def scrape(self, source, selectors):
        results = []
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "fr-TN,fr;q=0.9,en;q=0.8",
            "Referer": "https://www.google.com/",
        }
        async with httpx.AsyncClient(timeout=30, follow_redirects=True, headers=headers) as client:
            try:
                resp = await client.get(source.base_url)
                resp.raise_for_status()
            except Exception as exc:
                return results, str(exc)

        parser = HTMLParser(resp.text)
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
            """Collect all image URLs, preferring data-src (lazy loading) over src."""
            if not selector:
                return ""
            nodes = container.css(selector)
            urls = []
            for node in nodes:
                url = node.attributes.get("data-src") or node.attributes.get("src", "")
                if url and not url.startswith("data:"):
                    urls.append(url)
            return ",".join(urls)

        title = get(selectors.get("title", ""))
        price_raw = get(selectors.get("price", ""))
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

        return {
            "title": title,
            "price": normalize_tunisian_price(price_raw),
            "price_raw": price_raw,
            "stock": stock,
            "images": images_raw,
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
            """Collect all image URLs, preferring data-src (lazy loading) over src."""
            if not selector:
                return ""
            nodes = container.css(selector)
            urls = []
            for node in nodes:
                url = node.attributes.get("data-src") or node.attributes.get("src", "")
                if url and not url.startswith("data:"):
                    urls.append(url)
            return ",".join(urls)

        title = get(selectors.get("title", ""))
        price_raw = get(selectors.get("price", ""))
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

        return {
            "title": title,
            "price": normalize_tunisian_price(price_raw),
            "price_raw": price_raw,
            "stock": stock,
            "images": images_raw,
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
