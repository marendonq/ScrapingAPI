from __future__ import annotations
import json
from typing import Any, Dict, List
from urllib.parse import urljoin, urlparse
from selectolax.parser import HTMLParser

from ..utils.text import html_to_text, normalize_whitespace, to_float_price, slugify


# ---------- Helpers JSON-LD ----------
def _extract_jsonld_blocks(html: str) -> list[dict]:
    """
    Extrae y normaliza todos los bloques JSON-LD presentes en un HTML.

    Recorre los <script type="application/ld+json">, intenta parsearlos con `json.loads`
    y devuelve una lista de objetos (dicts o elementos válidos) listos para ser consumidos
    por otros parsers de nivel superior.

    Args:
        html: Cadena HTML completa de la página.

    Returns:
        Lista de bloques JSON-LD (cada elemento es típicamente un `dict`).

    Variables internas:
        tree: Árbol DOM generado por Selectolax para buscar los <script>.
        blocks: Acumulador con los bloques JSON-LD extraídos.
        raw: Texto crudo del script antes de parsear.
        data: Resultado del `json.loads`. Puede ser dict o list de dicts.
    """
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
    """
    Devuelve el primer valor "no vacío" de una secuencia.

    Considera como "vacío" a: None, "", [], {}.
    Útil para seleccionar el primer campo disponible entre varias alternativas.

    Args:
        *vals: Secuencia de valores candidatos.

    Returns:
        El primer valor no vacío o None si todos son vacíos.
    """
    for v in vals:
        if v not in (None, "", [], {}):
            return v
    return None


def _abs_url(base_url: str, href: str | None) -> str | None:
    """
    Construye una URL absoluta a partir de una base y un href relativo/absoluto.

    Si `href` ya es absoluto (empieza por http) se retorna tal cual; en caso contrario
    se resuelve con respecto a `base_url`.

    Args:
        base_url: URL base del sitio (p. ej., "https://tienda.com").
        href: Enlace tal como aparece en el HTML (relativo o absoluto).

    Returns:
        URL absoluta o None si `href` es None.

    Variables internas:
        (sin variables adicionales; usa `urljoin` directamente)
    """
    if not href:
        return None
    if href.startswith("http"):
        return href
    return urljoin(base_url.rstrip("/") + "/", href)


def _slug_from_url(url: str | None) -> str | None:
    """
    Obtiene un "slug" a partir de la ruta de una URL.

    Toma el último segmento de la ruta (separado por "/"), sin query ni fragment.

    Args:
        url: URL completa desde la cual extraer el segmento final.

    Returns:
        Slug (último segmento de la ruta) o None si no hay ruta o `url` es None.

    Variables internas:
        path: Ruta de la URL (p. ej., "/categoria/producto-123").
        segs: Segmentos no vacíos de la ruta.
    """
    if not url:
        return None
    path = urlparse(url).path
    if not path:
        return None
    segs = [s for s in path.strip("/").split("/") if s]
    return segs[-1] if segs else None


# ---------- Productos desde ItemList/Product ----------
def _product_from_jsonld(prod: dict) -> dict:
    """
    Normaliza un objeto JSON-LD de tipo Product a un dict canónico del dominio.

    Lee campos comunes como nombre, descripción (limpia HTML), precio/divisa desde
    `offers`, SKU/MPN, marca y URLs relevantes.

    Args:
        prod: Objeto JSON-LD que representa un Product (o compatible).

    Returns:
        Dict con las claves:
            - nombre (str)
            - descripcion (str | None)
            - precio (float | None)
            - divisa (str | None)
            - url_producto (str | None)
            - image_url (str | list | None)  # según el JSON-LD
            - sku (str | None)
            - brand (str | None)

    Variables internas:
        url: URL del producto desde @id o url.
        name: Nombre del producto.
        image: Imagen o lista de imágenes según el JSON-LD.
        brand: Marca (normalizada desde dict o str).
        description_html: Descripción en HTML, para limpiarla a texto.
        descripcion: Descripción limpia en texto plano.
        sku: Código de producto (sku o mpn).
        price, currency: Precio y divisa tomados de offers (incluye fallback a offers.offers[0]).
        offers: Objeto offers del JSON-LD (puede ser dict o list en algunos sitios).
    """
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
    """
    Extrae productos desde bloques JSON-LD de tipo ItemList o Product presentes en un HTML.

    Flujo:
      1) Busca un `ItemList` y mapea sus `itemListElement[*].item` a productos normalizados.
      2) Si no hay `ItemList`, busca directamente bloques `Product` sueltos y los normaliza.

    Args:
        html: Cadena HTML de la página (listado o detalle).

    Returns:
        Lista de dicts de producto tal como los retorna `_product_from_jsonld`.

    Variables internas:
        blocks: Bloques JSON-LD extraídos del HTML.
        items: Acumulador con los productos ya normalizados.
        le: Entrada de `itemListElement` (cada ítem de la lista).
        prod: Objeto JSON-LD candidato a Product dentro de cada `le`.
    """
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
    """
    Obtiene el rastro de migas (breadcrumbs) como lista de dicts con name/slug/url.

    Intenta primero leer un bloque JSON-LD de tipo `BreadcrumbList`.
    Si no existe o está incompleto, aplica un fallback al DOM buscando enlaces de
    un contenedor de breadcrumbs conocido.

    Args:
        html: Cadena HTML del detalle (o cualquier página con breadcrumbs).
        base_url: URL base del sitio para resolver enlaces relativos.

    Returns:
        Lista de dicts con las claves:
            - name: Texto visible de la categoría/nodo.
            - slug: Identificador amigable (desde URL o generado con `slugify`).
            - url: Enlace absoluto a cada nivel del breadcrumb.

    Variables internas:
        blocks: Bloques JSON-LD extraídos.
        path: Acumulador del breadcrumb resultante.
        li: Cada elemento de `itemListElement` dentro del JSON-LD.
        item: Nodo `item` (si viene como dict) dentro de `li`.
        name, url, url_abs: Nombre y URLs (original y absoluta).
        slug: Slug derivado de la URL absoluta o del `name`.
        tree: Árbol DOM Selectolax usado en el fallback cuando no hay JSON-LD.
        a: Cada enlace <a> encontrado en el contenedor breadcrumb del DOM.
    """
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
                url = (item or li).get("@id") or (item or li).get("url") or li.get("item")
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
    Devuelve el primer Product encontrado en el HTML en formato normalizado.

    Busca en:
      1) Bloques JSON-LD con @type == "Product".
      2) Bloques con la clave "@graph" que contengan un nodo de tipo "Product".

    Args:
        html: Cadena HTML de una página de detalle (o similar) que contenga JSON-LD.

    Returns:
        Un dict con el formato de `_product_from_jsonld` si encuentra un Product;
        de lo contrario, None.

    Variables internas:
        blocks: Bloques JSON-LD extraídos del HTML.
        node: Cada nodo dentro de un @graph (si aplica) que podría ser Product.
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
