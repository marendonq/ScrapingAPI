from __future__ import annotations
import asyncio
import re
from urllib.parse import urljoin
from typing import List

from ..config import settings
from ..http.client import HttpClient
from ..parsers.base import ListParser, DetailParser
from ..domain.models import Product
from ..domain.repositories import ProductRepository

class ScrapingService:
    """
    Orquestador de scraping:
    - Pagina por ?page=N
    - Extrae nombre, precio, url desde listado
    - Completa descripción desde detalle (concurrencia)
    - Asigna IDs, guarda en repositorio
    """
    def __init__(
        self,
        http: HttpClient,
        list_parser: ListParser,
        detail_parser: DetailParser,
        repo: ProductRepository,
        base_url: str,
        start_path: str,
    ) -> None:
        self.http = http
        self.list_parser = list_parser
        self.detail_parser = detail_parser
        self.repo = repo
        self.base_url = base_url.rstrip("/")
        self.start_path = start_path

    def _page_url(self, page: int) -> str:
        # reemplaza page=NUM en el path inicial
        return urljoin(self.base_url, re.sub(r"page=\d+", f"page={page}", self.start_path))

    def _abs(self, href: str) -> str:
        return urljoin(self.base_url + "/", href)

    async def _fetch_list_page(self, page: int) -> list[dict]:
        url = self._page_url(page)
        html = await self.http.get_text(url)
        items = self.list_parser.parse_items(html)
        # normaliza URL absoluta
        for it in items:
            it["url_producto"] = self._abs(it["href"])
            del it["href"]
        return items

    async def _fetch_description(self, url: str) -> str | None:
        html = await self.http.get_text(url)
        return self.detail_parser.parse_description(html)

    async def _enrich(self, items: list[dict]) -> list[Product]:
        sem = asyncio.Semaphore(settings.CONCURRENCY)

        async def worker(it: dict) -> Product | None:
            async with sem:
                try:
                    desc = await self._fetch_description(it["url_producto"])
                    return Product(
                        nombre=it["nombre"],
                        precio=it["precio"],
                        descripcion=desc,
                        url_producto=it["url_producto"],
                    )
                except Exception:
                    return None

        tasks = [asyncio.create_task(worker(it)) for it in items]
        results = await asyncio.gather(*tasks, return_exceptions=False)
        return [p for p in results if p is not None]

    async def scrape_all(self) -> list[Product]:
        page = 1
        seen = set()
        collected: list[dict] = []

        while True:
            if settings.MAX_PAGES and page > settings.MAX_PAGES:
                break

            items = await self._fetch_list_page(page)
            new_items = [it for it in items if it["url_producto"] not in seen]
            if not new_items:
                break

            for it in new_items:
                seen.add(it["url_producto"])
            collected.extend(new_items)

            page += 1
            await asyncio.sleep(settings.PAGE_DELAY_SECS)

        products = await self._enrich(collected)
        # asigna IDs incrementales
        for idx, p in enumerate(products, start=1):
            p.id = idx

        await self.repo.save_many(products)
        return products

    async def list_products(self) -> list[Product]:
        return await self.repo.list_all()
