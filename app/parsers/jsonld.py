from __future__ import annotations
import json
from typing import Any, Dict, List
from urllib.parse import urljoin, urlparse
from selectolax.parser import HTMLParser

from ..utils.text import html_to_text, normalize_whitespace, to_float_price, slugify

# ---------- Helpers JSON-LD ----------
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
            blocks.extend([x for x in data if isinstance(x, (dict, list))]) # type: ignore
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

# ---------- Productos desde ItemList/Product ----------
def _product_from_jsonld(prod: dict) -> dict:
    url = _first(prod.get("@id"), prod.get("url"))
    name = prod.get("name")
    image = prod.get("image")
    brand = None
    if isinstance(prod.get("brand"), dict):
        brand = prod["brand"].get("name") or prod["brand"].get("@id")
    elif isinstance(prod.get("brand"), str):
        brand = prod.get("brand")

    description_html = prod.get("description")
    descripcion = html_to_text(description_html)

    sku = prod.get("sku") or prod.get("mpn")
    price, currency = None, None
    offers = prod.get("offers")
    if isinstance(offers, dict):
        price = _first(offers.get("lowPrice"), offers.get("price"))
        currency = _first(offers.get("priceCurrency"))
        if price is None and isinstance(offers.get("offers"), list) and offers["offers"]:
            inner = offers["offers"][0]
            price = _first(inner.get("price"))
            currency = _first(currency, inner.get("priceCurrency"))

    return {
        "nombre": normalize_whitespace(name) or "",
        "descripcion": descripcion,
        "precio": to_float_price(price),
        "divisa": currency,
        "url_producto": url,
        "image_url": image,
        "sku": str(sku) if sku is not None else None,
        "brand": normalize_whitespace(brand),
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

# ---------- Breadcrumbs: JSON-LD -> fallback DOM ----------
def parse_breadcrumbs(html: str, base_url: str) -> list[dict]:
    blocks = _extract_jsonld_blocks(html)

    # 1) JSON-LD BreadcrumbList (preferido)
    for b in blocks:
        if isinstance(b, dict) and b.get("@type") == "BreadcrumbList":
            path: list[dict] = []
            for li in b.get("itemListElement", []):
                if not isinstance(li, dict):
                    continue
                item = li.get("item") if isinstance(li.get("item"), dict) else None
                name = (item or li).get("name")
                url  = (item or li).get("@id") or (item or li).get("url") or li.get("item")
                url_abs = _abs_url(base_url, url)
                slug = _slug_from_url(url_abs) or slugify(name)
                path.append({"name": normalize_whitespace(name), "slug": slug, "url": url_abs})
            # quita "Inicio" o raíz vacía
            path = [p for p in path if p.get("slug")]
            if path:
                return path
                

    # 2) Fallback DOM (como tu captura)
    tree = HTMLParser(html)
    path: list[dict] = []
    for a in tree.css('div[data-testid="breadcrumb"] a.vtex-breadcrumb-1-x-link[href]'):
        name = a.text(strip=True)
        href = a.attributes.get("href")
        url_abs = _abs_url(base_url, href)
        slug = _slug_from_url(url_abs) or slugify(name)
        path.append({"name": normalize_whitespace(name), "slug": slug, "url": url_abs})
    # filtra raíz
    path = [p for p in path if p.get("slug")]
    return path

def parse_first_product_jsonld(html: str) -> dict | None:
        """
        Devuelve un dict estilo _product_from_jsonld() si hay un Product único en el detalle.
        """
        blocks = _extract_jsonld_blocks(html)
        for b in blocks:
            if isinstance(b, dict) and b.get("@type") == "Product":
                return _product_from_jsonld(b)
        # A veces viene en @graph
        for b in blocks:
            if isinstance(b, dict) and isinstance(b.get("@graph"), list):
                for node in b["@graph"]:
                    if isinstance(node, dict) and node.get("@type") == "Product":
                        return _product_from_jsonld(node)
        return None