from __future__ import annotations
import asyncio, re
from urllib.parse import urljoin
import logging

from ..config import settings
from ..http.client import HttpClient
from ..domain.models import Product
from ..domain.repositories import ProductRepository, NoopCategoryRepository
from ..utils.text import truncate, coerce_str_id
from ..parsers.jsonld import (
    parse_itemlist_products,
    parse_breadcrumbs,
    parse_first_product_jsonld
)
logger = logging.getLogger(__name__)

class ScrapingService:
    def __init__(
        self,
        http: HttpClient,
        product_repo: ProductRepository,
        category_repo: NoopCategoryRepository,
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
        rows = parse_itemlist_products(html)

        products: list[Product] = []
        for it in rows:
            url_abs = it["url_producto"]
            if url_abs and not str(url_abs).startswith("http"):
                url_abs = urljoin(self.base_url + "/", str(url_abs))

            p = Product(
                nombre_producto=it["nombre_producto"],
                sku_id=it["sku_id"],
                product_id=it["product_id"],
                marca=it["marca"],
                categoria_comerciante_id=it["categoria_comerciante"],
                categoria_id=it["categoria_id"],
                nombre_categoria=it["nombre_categoria"],
                unidad=it["unidad"],
                precio=it["precio"],
                tipo_precio=it["tipo_precio"],
                imagen=it["imagen"],
                url_producto=url_abs,  # type: ignore
                categorias=[],         # se llenan en el enriquecimiento
            )
            products.append(p)
        return products

    from ..utils.text import truncate, coerce_str_id



    async def _enrich_from_detail(self, products: list[Product]) -> None:
        sem = asyncio.Semaphore(settings.CONCURRENCY)

        async def work(p: Product):
            try:
                async with sem:
                    html = await self.http.get_text(str(p.url_producto))
                    logger.info("enrich:start url=%s", p.url_producto)

                    crumbs = parse_breadcrumbs(html, self.base_url) or []
                    logger.info("enrich:crumbs url=%s count=%s last=%s",
                                p.url_producto, len(crumbs), (crumbs[-1] if crumbs else None))

                    # ⚠️ A veces el último breadcrumb es el producto: usa el penúltimo si coincide
                    chosen = None
                    if crumbs:
                        prod_slug = (str(p.url_producto).rstrip("/").split("/")[-1] or "").lower()
                        # filtra home/producto
                        candidates = [c for c in crumbs if (c.get("slug") or "").lower() not in {"home", "", prod_slug}]
                        chosen = (candidates[-1] if candidates else (crumbs[-2] if len(crumbs) >= 2 else crumbs[-1]))

                    if chosen:
                        p.nombre_categoria = p.nombre_categoria or truncate(chosen.get("name"), 128)
                        p.categoria_id = p.categoria_id or coerce_str_id(chosen.get("slug"), 12)

                    prod_detail = parse_first_product_jsonld(html)
                    logger.info("enrich:detail url=%s found=%s", p.url_producto, bool(prod_detail))

                    if prod_detail:
                        p.imagen = p.imagen or prod_detail.get("imagen")
                        p.marca = p.marca or truncate(prod_detail.get("marca"), 64)
                        p.sku_id = p.sku_id or coerce_str_id(prod_detail.get("sku_id") or prod_detail.get("product_id"), 12)
                        if p.precio is None:
                            p.precio = prod_detail.get("precio")

                    logger.info("enrich:result url=%s categoria=%s codigo=%s",
                                p.url_producto, p.nombre_categoria, p.categoria_id)
            except Exception as e:
                logger.exception("enrich:error url=%s err=%r", p.url_producto, e)

        await asyncio.gather(*(asyncio.create_task(work(p)) for p in products))

    async def scrape_all(self) -> list[Product]:
        page = 1
        seen: set[str] = set()
        collected: list[Product] = []

        while True:
            if settings.MAX_PAGES and page > settings.MAX_PAGES:
                break

            items = await self._fetch_list_page(page)

            # 🔧 Romper solo si la página no trae nada
            if not items:
                break

            # Deduplicación estable
            new_items = [it for it in items if str(it.url_producto) not in seen]
            for it in items:  # <-- importante: marcar todos como vistos
                seen.add(str(it.url_producto))

            if new_items:
                collected.extend(new_items)

            page += 1
            await asyncio.sleep(settings.PAGE_DELAY_SECS)

        if settings.ENRICH_FROM_PRODUCT_DETAIL and collected:
            await self._enrich_from_detail(collected)

        await self.product_repo.save_many(collected)
        return collected


    async def list_products(self) -> list[Product]:
        return await self.product_repo.list_all()
