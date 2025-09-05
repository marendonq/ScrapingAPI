# app/parsers/vtex_rest.py
from __future__ import annotations
from typing import Any, Dict, List, Optional
from app.domain.models import Product
from app.utils.text import normalize_whitespace  # asumiendo que ya existe

def _first_image_url(item: Dict[str, Any]) -> Optional[str]:
    # VTEX suele tener item["images"][{imageUrl, imageLabel, ...}] o "images" dentro del SKU
    images = item.get("images") or item.get("Images") or []
    if images and isinstance(images, list):
        # Cada image puede traer "imageUrl" o "imageUrl" sin protocolo
        url = images[0].get("imageUrl") or images[0].get("imageUrlText")
        if url:
            return url
    return None

def _price_block(item: Dict[str, Any]) -> tuple[Optional[float], Optional[str]]:
    # sellers -> [ { commertialOffer: { Price, ListPrice, ... , AvailableQuantity } } ]
    sellers = item.get("sellers") or item.get("Sellers") or []
    if sellers:
        co = (sellers[0].get("commertialOffer") or {}) if isinstance(sellers[0], dict) else {}
        # Usa Price si está; de lo contrario intenta otros campos típicos
        price = co.get("Price") or co.get("price") or co.get("ListPrice") or None
        # PriceType no siempre existe; dejemos "NORMAL" si hay price, None si no.
        price_type = co.get("priceCurrency") or "NORMAL" if price is not None else None
        try:
            return (float(price), price_type) if price is not None else (None, None)
        except Exception:
            return (None, None)
    return (None, None)

def _category_from_product(p: Dict[str, Any]) -> tuple[Optional[str], Optional[str]]:
    # VTEX REST puede exponer "categoryId" y/o un "categories" array con paths
    cat_id = p.get("categoryId") or p.get("CategoryId") or None
    # Nombre de la categoría no siempre viene directo; intenta "categories" último segmento
    cat_name = None
    cats = p.get("categories") or p.get("Categories") or []
    if cats and isinstance(cats, list):
        # suelen venir paths tipo "/Alimentos/Despensa/Arroces/"
        last = cats[-1]
        if isinstance(last, str):
            last = last.strip("/").split("/")[-1]
            cat_name = last or None
    return (str(cat_id) if cat_id not in (None, "") else None, cat_name)

def parse_vtex_rest(items: List[Dict[str, Any]], base_url: str) -> List[Product]:
    """
    Transforma el payload de /api/catalog_system/pub/products/search en objetos Product.
    Reglas:
      - Tantos rows como SKUs (items) tenga cada producto.
      - Campos ausentes -> None.
    """
    out: List[Product] = []

    for p in items or []:
        product_id = str(p.get("productId") or p.get("ProductId") or "") or None
        brand = normalize_whitespace(p.get("brand") or p.get("Brand") or None)
        name = normalize_whitespace(p.get("productName") or p.get("productTitle") or p.get("ProductName") or None)
        link = p.get("linkText") or p.get("link") or None
        product_url = f"{base_url}/{link}/p" if link else None
        category_id, category_name = _category_from_product(p)

        for it in (p.get("items") or p.get("Items") or []):
            sku = str(it.get("itemId") or it.get("ItemId") or "") or None
            image_url = _first_image_url(it)
            price, price_type = _price_block(it)

            # Si tienes una función propia para unidad, úsala; si no, inferimos muy básico
            unit = it.get("measurementUnit") or it.get("unitMultiplier") or None
            # Ajuste simple: measurementUnit a veces trae "un", "kg", etc.; si es vacío, deja None
            unit = str(unit) if unit not in (None, "", "0") else None

            # Mapea a tu Product (ajusta nombres si tu modelo usa snake_case distinto)
            prod = Product(
                sku_id=sku,                    # <- ajusta si tu campo se llama distinto
                product_id=product_id,
                nombre_producto=name,
                marca=brand,
                categoria_comerciante_id=None,     # Euro no lo expone; deja None
                categoria_id=category_id,
                nombre_categoria=category_name,  # o category_name, según tu modelo
                unidad=unit,
                precio=price,
                tipo_precio=price_type,
                imagen=image_url,
                url_producto=product_url,
            )
            out.append(prod)

    return out
