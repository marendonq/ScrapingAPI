from __future__ import annotations
from typing import Protocol, Iterable
from selectolax.parser import HTMLParser

class ListItem(Protocol):
    nombre: str
    precio: float | None
    url_producto: str

class ListParser(Protocol):
    """
    Interfaz para parsear páginas de listado.
    """
    def parse_items(self, html: str) -> list[dict]: ...

class DetailParser(Protocol):
    """
    Interfaz para parsear páginas de detalle (descripción).
    """
    def parse_description(self, html: str) -> str | None: ...
