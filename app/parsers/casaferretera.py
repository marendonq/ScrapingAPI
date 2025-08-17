from __future__ import annotations
from selectolax.parser import HTMLParser
from .base import ListParser, DetailParser
from ..utils.text import normalize_whitespace, to_float_price

# ====== SELECTORES: AJUSTA A LA PÁGINA REAL ======
SELECTOR_ITEM = 'section.vtex-product-summary-2-x-container[aria-label^="Producto"]'
SEL_NOMBRE    = 'h3.vtex-product-summary-2-x-productNameContainer'
SEL_NOMBRE_FALLBACK = 'div.vtex-product-summary-2-x-nameContainer[aria-label^="Nombre del producto"]'
SEL_PRECIO    = 'span.vtex-product-price-1-x-sellingPriceValue'
SEL_LINK      = 'a.vtex-product-summary-2-x-clearLink[href]'
SEL_DESC_DETALLE = 'p.casaferretera-modulos-1-x-descripcionproduct'

class CasaFerreteraListParser(ListParser):
    """
    Responsabilidad: extraer items (nombre, precio, url) de páginas de listado.
    """
    def parse_items(self, html: str) -> list[dict]:
        tree = HTMLParser(html)
        items: list[dict] = []

        for node in tree.css(SELECTOR_ITEM):
            name = node.css_first(SEL_NOMBRE) or node.css_first(SEL_NOMBRE_FALLBACK)
            link = node.css_first(SEL_LINK)
            if not (name and link):
                continue
            price = node.css_first(SEL_PRECIO)
            nombre = normalize_whitespace(name.text(strip=True)) if name else None
            precio = to_float_price(price.text(strip=True) if price else None)
            href = link.attributes.get("href")
            if not href:
                continue
            items.append({
                "nombre": nombre,
                "precio": precio,
                "href": href
            })
        return items


class CasaFerreteraDetailParser(DetailParser):
    """
    Responsabilidad: extraer descripción desde la página de detalle.
    """
    def parse_description(self, html: str) -> str | None:
        tree = HTMLParser(html)
        node = tree.css_first(SEL_DESC_DETALLE)
        if not node:
            return None
        return normalize_whitespace(node.text(separator=" ", strip=True))
