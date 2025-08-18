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
    """
    Caso de uso principal para realizar el scraping de productos y su persistencia.

    Orquesta:
      - Descarga de páginas de listado.
      - Parseo de productos desde JSON-LD.
      - Enriquecimiento por detalle (breadcrumbs → categorías, y campos del Product JSON-LD).
      - Persistencia usando los repositorios de productos y categorías.

    Atributos:
        http: Cliente HTTP asíncrono para obtener HTML.
        product_repo: Repositorio para guardar/listar productos.
        category_repo: Repositorio para crear/asegurar categorías a partir de breadcrumbs.
        base_url: URL base del sitio (sin slash final).
        start_path: Ruta inicial del listado (debe incluir un query con `page=...`).

    Notas:
        Los parámetros de concurrencia, demoras y límites se leen desde `settings`
        (p. ej., CONCURRENCY, PAGE_DELAY_SECS, MAX_PAGES).
    """

    def __init__(
        self,
        http: HttpClient,
        product_repo: ProductRepository,
        category_repo: CategoryRepository,
        base_url: str,
        start_path: str,
    ) -> None:
        """
        Inicializa el servicio de scraping con sus dependencias e información base.

        Args:
            http: Cliente HTTP para descargar páginas.
            product_repo: Implementación del repositorio de productos.
            category_repo: Implementación del repositorio de categorías.
            base_url: Dominio base (p. ej., "https://www.sitio.com").
            start_path: Ruta de la página de listado con el parámetro `page` en el query.

        Efectos:
            Normaliza `base_url` removiendo un posible slash final.
        """
        self.http = http
        self.product_repo = product_repo
        self.category_repo = category_repo
        self.base_url = base_url.rstrip("/")
        self.start_path = start_path

    def _page_url(self, page: int) -> str:
        """
        Construye la URL absoluta del listado para una página concreta.

        Reemplaza el valor de `page=...` en `start_path` y lo une con `base_url`.

        Args:
            page: Número de página (>= 1).

        Returns:
            URL absoluta de la página de listado solicitada.

        Variables internas:
            (usa `re.sub` para reemplazar el valor de page y `urljoin` para resolver la URL)
        """
        return urljoin(self.base_url, re.sub(r"page=\d+", f"page={page}", self.start_path))

    async def _fetch_list_page(self, page: int) -> list[Product]:
        """
        Descarga y parsea una página de listado para obtener productos básicos.

        Flujo:
          1) Construye URL con `_page_url(page)` y descarga HTML.
          2) Extrae productos desde JSON-LD `ItemList` (o `Product` sueltos) con `parse_itemlist_products`.
          3) Normaliza cada producto a `Product` del dominio (sin categorías aún).

        Args:
            page: Número de página a solicitar.

        Returns:
            Lista de instancias `Product` con campos básicos (nombre, descripcion, precio,
            divisa, url_producto, image_url, sku, brand). `categorias`, `categoria`,
            `codigo_categoria` se dejan para el enriquecimiento.

        Variables internas:
            url: URL absoluta de la página de listado.
            html: HTML descargado de la página.
            rows: Lista de dicts normalizados desde el JSON-LD del listado.
            products: Acumulador de objetos `Product` instanciados.
            it: Dict individual con los campos normalizados de un producto.
            url_abs: URL absoluta del producto (corrige si vino relativa).
            p: Instancia `Product` creada a partir de `it`.
        """
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
                url_producto=url_abs,  # type: ignore
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
        Enriquecimiento por detalle para una lista de productos (in-place).

        Para cada producto:
          - Descarga su HTML de detalle.
          - Obtiene breadcrumbs (JSON-LD `BreadcrumbList` o fallback DOM) y asegura
            las categorías en el repositorio, guardando los objetos con ID.
          - (Opcional) Completa campos vacíos con datos del JSON-LD `Product` del detalle.

        Args:
            products: Lista de instancias `Product` a enriquecer.

        Returns:
            None. Modifica los objetos `Product` recibidos (asigna categorías, posible
            actualización de descripcion, image_url, sku, brand).

        Variables internas:
            sem: Semáforo para limitar concurrencia según `settings.CONCURRENCY`.
            work(p): Corrutina que procesa un único producto:
                - html: HTML del detalle del producto.
                - crumbs: Lista de dicts [{"name","slug","url"}, ...] del breadcrumb.
                - cat_objs: Objetos de categoría persistidos/asegurados (con ID).
                - prod_detail: Dict con campos normalizados del `Product` del detalle (si existe).
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
        """
        Ejecuta el scraping completo de listados, enriquece y persiste productos.

        Estrategia:
          - Pagina desde `page=1` hasta agotar resultados o superar `settings.MAX_PAGES`.
          - Evita duplicados con un conjunto `seen` basado en `url_producto`.
          - Aplica una pausa entre páginas (`settings.PAGE_DELAY_SECS`).
          - Si `settings.ENRICH_FROM_PRODUCT_DETAIL` es True, enriquece los productos
            con breadcrumbs y datos del detalle.
          - Asigna IDs incrementales temporales antes de guardar.
          - Persiste todos los productos mediante `product_repo.save_many`.

        Returns:
            Lista final de `Product` procesados y persistidos.

        Variables internas:
            page: Contador de página actual.
            seen: Conjunto de URLs ya vistas para evitar duplicados.
            collected: Lista acumulada de productos nuevos.
            items: Productos básicos obtenidos en la página actual.
            new_items: Subconjunto de `items` que no estaban en `seen`.
            idx, p: Enumeración para asignar IDs temporales.
        """
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
        """
        Retorna todos los productos persistidos mediante el repositorio.

        Returns:
            Lista de `Product` tal como los devuelve `product_repo.list_all()`.
        """
        return await self.product_repo.list_all()
