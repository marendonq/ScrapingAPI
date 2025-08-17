from __future__ import annotations
from typing import Protocol, List
from .models import Product

class ProductRepository(Protocol):
    """
    Puerto (interfaz) de persistencia: bajo acoplamiento.
    """
    async def save_many(self, products: list[Product]) -> None: ...
    async def list_all(self) -> list[Product]: ...

class InMemoryProductRepository:
    """
    Adaptador en memoria: útil para respuestas API inmediatas.
    """
    def __init__(self) -> None:
        self._items: list[Product] = []

    async def save_many(self, products: list[Product]) -> None:
        self._items = products

    async def list_all(self) -> list[Product]:
        return list(self._items)
