from __future__ import annotations
import json
from urllib.parse import urljoin, urlparse
from selectolax.parser import HTMLParser

from ..utils.text import (
    html_to_text,
    normalize_whitespace,
    slugify,
    to_decimal_price,
    coerce_str_id,
    truncate,
    infer_unidad_from_title,
)

def _extract_jsonld_blocks(html: str) -> list[dict]:
    tree = HTMLParser(html)
    blocks: list[dict] = []
    for script in tree.css('script[type="application/ld+json"]'):
        raw = script.text(strip=True)
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(data, list):
            blocks.extend([x for x in data if isinstance(x, (dict, list))])  # type: ignore
        else:
            blocks.append(data)
    return blocks

def _first(*vals):
    for v in vals:
        if v not in (None, "", [], {}):
            return v
    return None

def _abs_url(base_url: str, href: str | None) -> str | None:
    if not href:
        return None
    if href.startswith("http"):
        return href
    return urljoin(base_url.rstrip("/") + "/", href)

def _slug_from_url(url: str | None) -> str | None:
    if not url:
        return None
    path = urlparse(url).path
    if not path:
        return None
    segs = [s for s in path.strip("/").split("/") if s]
    return segs[-1] if segs else None

def _product_from_jsonld(prod: dict) -> dict:
    url = _first(prod.get("@id"), prod.get("url"))
    name = normalize_whitespace(prod.get("name")) or ""

    # brand puede venir como dict o str
    brand = None
    if isinstance(prod.get("brand"), dict):
        brand = prod["brand"].get("name") or prod["brand"].get("@id")
    elif isinstance(prod.get("brand"), str):
        brand = prod.get("brand")
    brand = normalize_whitespace(brand)

    sku = prod.get("sku")
    image = prod.get("image")

    # Precio
    price,tipo_precio = None , None
    offers = prod.get("offers")
    if isinstance(offers, dict):
        price = _first(offers.get("lowPrice"), offers.get("price"))
        tipo_precio = _first(offers.get("priceCurrency"))
        # Algunas tiendas anidan en offers["offers"][0]
        if (price is None or tipo_precio is None) and isinstance(offers.get("offers"), list) and offers["offers"]:
            inner = offers["offers"][0]
            if isinstance(inner, dict):
                price = _first(price, inner.get("price"), inner.get("lowPrice"))
                tipo_precio = _first(tipo_precio, inner.get("priceCurrency"))

    elif isinstance(offers, list) and offers:
        # También hay tiendas que ponen offers = [ {price, priceCurrency}, ... ]
        first_offer = offers[0]
        if isinstance(first_offer, dict):
            price = _first(first_offer.get("lowPrice"), first_offer.get("price"))
            tipo_precio = _first(first_offer.get("priceCurrency"))

    # Normalizaciones
    price = to_decimal_price(price)                 # Decimal cuantizado a 2
    tipo_precio = truncate(tipo_precio, 12) 

    unidad = infer_unidad_from_title(name)

    id_sku = coerce_str_id(sku, 12)

    return {
        # Campos target DB
        "sku_id": id_sku,
        "product_id": id_sku, 
        "nombre_producto": name,
        "marca": truncate(brand, 64),

        "categoria_comerciante": None,  # se puede derivar por reglas propias si hace falta
        "categoria_id": None,           # se completa desde breadcrumbs en enrich
        "nombre_categoria": None,       # se completa desde breadcrumbs en enrich

        "unidad": truncate(unidad, 12),

        "precio": price,
        "tipo_precio": tipo_precio,

        "imagen": image,
        "url_producto": url,
    }

def parse_itemlist_products(html: str) -> list[dict]:
    blocks = _extract_jsonld_blocks(html)
    items: list[dict] = []
    for b in blocks:
        if isinstance(b, dict) and b.get("@type") == "ItemList" and isinstance(b.get("itemListElement"), list):
            for le in b["itemListElement"]:
                if not isinstance(le, dict):
                    continue
                prod = le.get("item")
                if isinstance(prod, dict):
                    items.append(_product_from_jsonld(prod))
    if not items:
        for b in blocks:
            if isinstance(b, dict) and b.get("@type") == "Product":
                items.append(_product_from_jsonld(b))
    return items

def parse_breadcrumbs(html: str, base_url: str) -> list[dict]:
    blocks = _extract_jsonld_blocks(html)
    

    def _build_path(node: dict) -> list[dict]:
        path: list[dict] = []
        for li in node.get("itemListElement", []):
            if not isinstance(li, dict):
                continue
            # item puede ser dict o string (URL)
            item = li.get("item") if isinstance(li.get("item"), dict) else None
            name = (item or li).get("name")
            url = (item or li).get("@id") or (item or li).get("url") or li.get("item")
            url_abs = _abs_url(base_url, url)
            slug = _slug_from_url(url_abs) or slugify(name)
            path.append({"name": normalize_whitespace(name), "slug": slug, "url": url_abs})
        return [p for p in path if p.get("slug")]

    # 1) BreadcrumbList en la raíz del JSON-LD
    for b in blocks:
        if isinstance(b, dict) and b.get("@type") == "BreadcrumbList":
            path = _build_path(b)
            if path:
                return path

    # 2) BreadcrumbList dentro de @graph (muy común)
    for b in blocks:
        if isinstance(b, dict) and isinstance(b.get("@graph"), list):
            for node in b["@graph"]:
                if isinstance(node, dict) and node.get("@type") == "BreadcrumbList":
                    path = _build_path(node)
                    if path:
                        return path

    # 3) Fallback: HTML
    tree = HTMLParser(html)
    path: list[dict] = []
    for a in tree.css('div[data-testid="breadcrumb"] a.vtex-breadcrumb-1-x-link[href]'):
        name = a.text(strip=True)
        href = a.attributes.get("href")
        url_abs = _abs_url(base_url, href)
        slug = _slug_from_url(url_abs) or slugify(name)
        path.append({"name": normalize_whitespace(name), "slug": slug, "url": url_abs})
    path = [p for p in path if p.get("slug")]
    return path

def parse_first_product_jsonld(html: str) -> dict | None:
    blocks = _extract_jsonld_blocks(html)
    for b in blocks:
        if isinstance(b, dict) and b.get("@type") == "Product":
            return _product_from_jsonld(b)
    for b in blocks:
        if isinstance(b, dict) and isinstance(b.get("@graph"), list):
            for node in b["@graph"]:
                if isinstance(node, dict) and node.get("@type") == "Product":
                    return _product_from_jsonld(node)
    return None