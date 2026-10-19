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
        async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
            try:
                resp = await client.get(source.base_url, headers={"User-Agent": "KarthagoBot/1.0"})
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

        title = get(selectors.get("title", ""))
        price_raw = get(selectors.get("price", ""))
        stock_raw = get(selectors.get("stock", ""))
        images_raw = get(selectors.get("images", ""))

        return {
            "title": title,
            "price": normalize_tunisian_price(price_raw),
            "price_raw": price_raw,
            "stock": self._parse_stock(stock_raw),
            "images": images_raw,
        }

    @staticmethod
    def _parse_stock(raw):
        text = str(raw).lower()
        if any(k in text for k in ["out of stock", "épuisé", "non disponible", "0"]):
            return 0
        digits = "".join(ch for ch in text if ch.isdigit())
        return int(digits) if digits else 1


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

        title = get(selectors.get("title", ""))
        price_raw = get(selectors.get("price", ""))
        stock_raw = get(selectors.get("stock", ""))
        images_raw = get(selectors.get("images", ""))

        return {
            "title": title,
            "price": normalize_tunisian_price(price_raw),
            "price_raw": price_raw,
            "stock": self._parse_stock(stock_raw),
            "images": images_raw,
        }

    @staticmethod
    def _parse_stock(raw):
        text = str(raw).lower()
        if any(k in text for k in ["out of stock", "épuisé", "non disponible", "0"]):
            return 0
        digits = "".join(ch for ch in text if ch.isdigit())
        return int(digits) if digits else 1


def get_engine(engine_type):
    if engine_type == "DYNAMIC":
        return PlaywrightEngine()
    return HTTPEngine()
