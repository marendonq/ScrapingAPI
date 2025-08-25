from __future__ import annotations
from typing import Protocol, List, Dict, Optional
from .models import Product, Category
from ..utils.text import slugify

# -------- Productos --------
class ProductRepository(Protocol):
    async def save_many(self, products: list[Product]) -> None: ...
    async def list_all(self) -> list[Product]: ...

class InMemoryProductRepository:
    def __init__(self) -> None:
        self._items: list[Product] = []

    async def save_many(self, products: list[Product]) -> None:
        self._items = products

    async def list_all(self) -> list[Product]:
        return list(self._items)

# -------- Categorías --------
class NoopCategoryRepository:
    async def ensure_path(self, crumbs: list[dict]):
        return []  # no devuelve categorías; sólo permite que el servicio no falle

    async def list_all(self):
        return []
class InMemoryCategoryRepository:
    """
    Deduplica por `slug` (o slugify(name) si no viene). Asigna IDs incrementales.
    """
    def __init__(self) -> None:
        self._by_slug: Dict[str, Category] = {}
        self._auto_id: int = 1

    async def ensure_path(self, crumbs: list[dict]) -> list[Category]:
        out: list[Category] = []
        for c in crumbs:
            name = (c.get("name") or "").strip()
            slug = c.get("slug") or slugify(name) or ""
            url  = c.get("url")
            if slug == "":
                # si no hay forma de identificar, ignora este nivel
                continue

            cat = self._by_slug.get(slug)
            if not cat:
                cat = Category(id=self._auto_id, name=name, slug=slug, url=url)
                self._by_slug[slug] = cat
                self._auto_id += 1
            else:
                # opcional: refrescar nombre/url si llegan valores más “bonitos”
                if name and cat.name != name:
                    cat.name = name
                if url and not cat.url:
                    cat.url = url
            out.append(cat)
        return out

    async def list_all(self) -> list[Category]:
        # Mantiene el orden de inserción (dict es ordered)
        return list(self._by_slug.values())
