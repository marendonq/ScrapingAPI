from __future__ import annotations
import asyncio, re
from urllib.parse import urljoin

from ..config import settings
from ..http.client import HttpClient
from ..domain.models import Product
from ..domain.repositories import ProductRepository, CategoryRepository
from ..parsers.jsonld import (
    parse_itemlist_products,
    parse_breadcrumbs,
    parse_first_product_jsonld,
)

class ScrapingService:
    def __init__(
        self,
        http: HttpClient,
        product_repo: ProductRepository,
        category_repo: CategoryRepository,
        base_url: str,
        start_path: str,
    ) -> None:
        self.http = http
        self.product_repo = product_repo
        self.category_repo = category_repo
        self.base_url = base_url.rstrip("/")
        self.start_path = start_path

    def _page_url(self, page: int) -> str:
        return urljoin(self.base_url, re.sub(r"page=\d+", f"page={page}", self.start_path))

    async def _fetch_list_page(self, page: int) -> list[Product]:
        url = self._page_url(page)
        html = await self.http.get_text(url)

        rows = parse_itemlist_products(html)  # campos básicos desde el JSON-LD de la lista

        products: list[Product] = []
        for it in rows:
            url_abs = it["url_producto"]
            if url_abs and not str(url_abs).startswith("http"):
                url_abs = urljoin(self.base_url + "/", str(url_abs))
            p = Product(
                nombre=it["nombre"],
                descripcion=it["descripcion"],
                precio=it["precio"],
                divisa=it["divisa"],
                url_producto=url_abs, # type: ignore
                image_url=it["image_url"],
                sku=it["sku"],
                brand=it["brand"],
                categorias=[],          # se llenan en el enriquecimiento
                categoria=None,
                codigo_categoria=None,
            )
            products.append(p)
        return products

    async def _enrich_from_detail(self, products: list[Product]) -> None:
        """
        Para cada producto: descarga su página /.../p, extrae breadcrumbs y asegura categorías con ID.
        También puede completar/actualizar campos desde el Product JSON-LD del detalle.
        """
        sem = asyncio.Semaphore(settings.CONCURRENCY)

        async def work(p: Product):
            async with sem:
                html = await self.http.get_text(str(p.url_producto))

                # 1) Categorías por producto (JSON-LD BreadcrumbList o fallback DOM)
                crumbs = parse_breadcrumbs(html, self.base_url)  # [{"name","slug","url"},...]
                cat_objs = await self.category_repo.ensure_path(crumbs)
                p.categorias = cat_objs
                if cat_objs:
                    p.categoria = cat_objs[-1].name
                    p.codigo_categoria = cat_objs[-1].slug

                # 2) (Opcional) completar datos con Product del detalle (si vienen más precisos)
                prod_detail = parse_first_product_jsonld(html)
                if prod_detail:
                    # Solo completa si faltan o si quieres sobreescribir
                    p.descripcion = p.descripcion or prod_detail.get("descripcion")
                    p.image_url  = p.image_url  or prod_detail.get("image_url")
                    p.sku        = p.sku        or prod_detail.get("sku")
                    p.brand      = p.brand      or prod_detail.get("brand")
                    # precio/divisa suelen coincidir; si quieres sobreescribir, hazlo aquí:
                    # p.precio = prod_detail.get("precio") or p.precio
                    # p.divisa = prod_detail.get("divisa") or p.divisa

        tasks = [asyncio.create_task(work(p)) for p in products]
        await asyncio.gather(*tasks)

    async def scrape_all(self) -> list[Product]:
        page = 1
        seen = set()
        collected: list[Product] = []

        while True:
            if settings.MAX_PAGES and page > settings.MAX_PAGES:
                break

            items = await self._fetch_list_page(page)
            new_items = [it for it in items if str(it.url_producto) not in seen]
            if not new_items:
                break

            for it in new_items:
                seen.add(str(it.url_producto))
            collected.extend(new_items)

            page += 1
            await asyncio.sleep(settings.PAGE_DELAY_SECS)

        if settings.ENRICH_FROM_PRODUCT_DETAIL and collected:
            await self._enrich_from_detail(collected)

        for idx, p in enumerate(collected, start=1):
            p.id = idx

        await self.product_repo.save_many(collected)
        return collected

    async def list_products(self) -> list[Product]:
        return await self.product_repo.list_all()
