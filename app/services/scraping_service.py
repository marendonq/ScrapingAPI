from __future__ import annotations
from typing import Any, Dict, List, Set
import asyncio, re
from urllib.parse import urljoin
import logging
import httpx

from ..config import settings
from ..http.client import HttpClient
from ..domain.models import Product
from ..domain.repositories import ProductRepository, NoopCategoryRepository
from ..utils.text import truncate, coerce_str_id
from app.parsers.vtex_rest import parse_vtex_rest
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
    
    async def scrape_vtex_rest(self, qs: Dict[str, Any]) -> List[Product]:
        endpoint = qs.get("endpoint") or settings.EURO_ENDPOINT_DEFAULT
        page_size = int(qs.get("page_size") or settings.VTEX_PAGE_SIZE or 24)
        referer_path = qs.get("referer_path") or "/mercado"
        vtex_map = qs.get("map") or "c"

        def _is_internal(k: str) -> bool:
            return k in {"endpoint", "page_size", "referer_path", "map"}

        base_params = {k: v for k, v in qs.items() if not _is_internal(k)}
        base_params["map"] = vtex_map

        headers = {
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json",
            "Accept-Language": "es-CO,es;q=0.9",
            "Referer": f"{self.base_url}{referer_path}",
        }

        start = 0
        seen: Set[str] = set()
        collected: List[Product] = []

        # Usa el cliente ya inicializado por lifespan; no lo cierres aquí
        client = self.http.client

        while True:
            params = dict(base_params)
            params.update({"_from": start, "_to": start + page_size - 1})
            url = f"{self.base_url}{endpoint}"

            r = await client.get(url, params=params, headers=headers, follow_redirects=True)
            if r.status_code in (400, 416):
                logger.info("vtex: stop status=%s start=%s", r.status_code, start)
                break
            r.raise_for_status()

            payload = r.json() or []
            count_products = len(payload)
            if count_products == 0:
                logger.info("vtex: empty payload start=%s -> done", start)
                break

            parsed = parse_vtex_rest(payload, self.base_url)

            # Dedupe por sku_id
            new_rows: List[Product] = []
            for p in parsed:
                sku = getattr(p, "sku_id", None)
                if sku and sku not in seen:
                    seen.add(sku)
                    new_rows.append(p)

            collected.extend(new_rows)

            logger.info(
                "vtex: window start=%s got_products=%s got_skus=%s new_skus=%s total=%s",
                start, count_products, len(parsed), len(new_rows), len(collected)
            )

            # 👉 Heurística correcta: si VTEX devolvió menos productos que la ventana, se acabó
            if count_products < page_size:
                break

            start += page_size

        return collected
    
    async def save_products(self, products: list[Product]) -> int:
        if not products:
            return 0
        await self.product_repo.save_many(products)
        return len(products)
    
    # 1) Facets → hojas de categoría con root /mercado
    async def _vtex_list_leaf_categories(self, path: str = "/mercado", vtex_map: str = "c") -> list[dict]:
        url = f"{self.base_url}/api/catalog_system/pub/facets/search{path}"
        params = {"map": vtex_map}
        r = await self.http.client.get(url, params=params, headers={"Accept": "application/json"})
        r.raise_for_status()
        data = r.json() or {}

        trees = data.get("CategoriesTrees") or data.get("categoriesTrees") or []
        leaves: list[dict] = []

        def walk(nodes: list[dict]):
            for n in nodes or []:
                children = n.get("Children") or n.get("children") or []
                if children:
                    walk(children)
                else:
                    cid = str(n.get("Id") or n.get("id") or "")
                    name = n.get("Name") or n.get("name")
                    link = n.get("Link") or n.get("link") or None
                    if cid:
                        leaves.append({"id": cid, "name": name, "link": link})

        walk(trees)
        return leaves

    # 2) Búsqueda paginada por ventana (reutilizable)
    async def _vtex_windowed_search(self, endpoint: str, referer_path: str, base_params: dict, page_size: int) -> list[Product]:
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json",
            "Accept-Language": "es-CO,es;q=0.9",
            "Referer": f"{self.base_url}{referer_path}",
        }
        start = 0
        seen: set[str] = set()
        collected: list[Product] = []
        client = self.http.client

        while True:
            params = dict(base_params)
            params.update({"_from": start, "_to": start + page_size - 1})
            url = f"{self.base_url}{endpoint}"

            r = await client.get(url, params=params, headers=headers, follow_redirects=True)
            if r.status_code in (400, 416):
                break
            r.raise_for_status()

            payload = r.json() or []
            if not payload:
                break

            parsed = parse_vtex_rest(payload, self.base_url)

            for p in parsed:
                sku = getattr(p, "sku_id", None)
                if sku and sku not in seen:
                    seen.add(sku)
                    collected.append(p)

            if len(payload) < page_size:
                break
            start += page_size

        return collected

    # 3) Deep: particiona por hojas de categoría para evitar el tope ~2.6k
    async def scrape_vtex_rest_deep(self, qs: dict) -> list[Product]:
        endpoint = qs.get("endpoint") or settings.EURO_ENDPOINT_DEFAULT
        page_size = int(qs.get("page_size") or settings.VTEX_PAGE_SIZE or 50)
        referer_path = qs.get("referer_path") or "/mercado"
        vtex_map = qs.get("map") or "c"

        base_params = {k: v for k, v in qs.items() if k not in {"endpoint", "page_size", "referer_path", "map"}}
        base_params["map"] = vtex_map

        # 1) intento global (rápido); si trae poco, no está capado y sirve
        global_results = await self._vtex_windowed_search(endpoint, referer_path, base_params, page_size)
        if len(global_results) < 2400:
            return global_results

        # 2) capado detectado: shard por hojas de categoría
        leaves = await self._vtex_list_leaf_categories(path=referer_path, vtex_map=vtex_map)
        seen = {getattr(p, "sku_id") for p in global_results if getattr(p, "sku_id", None)}
        collected = list(global_results)

        for leaf in leaves:
            shard_params = dict(base_params)
            shard_params["fq"] = f"C:/{leaf['id']}/"
            shard_results = await self._vtex_windowed_search(endpoint, referer_path, shard_params, page_size)
            for p in shard_results:
                sku = getattr(p, "sku_id", None)
                if sku and sku not in seen:
                    seen.add(sku)
                    collected.append(p)

        return collected    

    async def list_products(self) -> list[Product]:
        return await self.product_repo.list_all()
    

