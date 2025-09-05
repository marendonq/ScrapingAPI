from __future__ import annotations
from fastapi import APIRouter, HTTPException, Depends, Query
from typing import Any, Dict, Optional
from ..domain.models import Product
from ..services.scraping_service import ScrapingService

router = APIRouter()
service: ScrapingService | None = None

def init_routes(scraping_service: ScrapingService) -> APIRouter:
    global service
    service = scraping_service
    return router

def get_service() -> ScrapingService:
    if service is None:
        raise HTTPException(500, "Service not initialized")
    return service

@router.get("/health")
async def health():
    return {"ok": True}

@router.post("/scrape")
async def run_scrape(service: ScrapingService = Depends(get_service)):
    prods = await service.scrape_all()
    return [p.model_dump(exclude={"categorias"}) for p in prods]

@router.get("/products")
async def list_products(service: ScrapingService = Depends(get_service)):
    prods = await service.list_products()
    return [p.model_dump(exclude={"categorias"}) for p in prods]

def _pass_qs(**qs: Any) -> Dict[str, Any]:
    # util simple para forwardear todo lo recibido
    return {k: v for k, v in qs.items() if v not in (None, "")}

@router.get("/scrape/vtex/rest")
async def scrape_vtex_rest(
    endpoint: Optional[str] = Query(default=None, description="Ruta VTEX-REST, ej: /api/catalog_system/pub/products/search/mercado"),
    page_size: Optional[int] = Query(default=None, ge=1, le=96),
    referer_path: Optional[str] = Query(default=None, description="Path para Referer, ej: /mercado"),
    map: Optional[str] = Query(default=None, description="VTEX map, ej: c"),
    fq: Optional[str] = Query(default=None, description="Filtro VTEX, ej: C:/139169/"),
    O: Optional[str] = Query(default=None, description="Orden, ej: OrderByPriceASC"),
    persist: bool = Query(default=False, description="Si true, guarda en PostgreSQL"),
    service: ScrapingService = Depends(get_service),
):
    qs = _pass_qs(endpoint=endpoint, page_size=page_size, referer_path=referer_path, map=map, fq=fq, O=O)
    products = await service.scrape_vtex_rest(qs)
    if persist and products:
        await service.save_products(products)
    return [p.model_dump() for p in products]
    # Si ya persistías en DB en otro endpoint, aquí sólo devolvemos; o puedes persistir también.
    return [p.model_dump() for p in products]  # si usas Pydantic v2; en v1 -> p.dict()

@router.get("/scrape/vtex/rest/deep")
async def scrape_vtex_rest_deep(
    endpoint: Optional[str] = Query(default=None),
    page_size: Optional[int] = Query(default=50, ge=1, le=50),
    referer_path: Optional[str] = Query(default="/mercado"),
    map: Optional[str] = Query(default="c"),
    persist: bool = Query(default=False, description="Si true, guarda en PostgreSQL"),
    fq: Optional[str] = Query(default=None),  # ignorado en deep; lo dejamos por compatibilidad
    O: Optional[str] = Query(default=None),
    service: ScrapingService = Depends(get_service),
):
    qs = {k: v for k, v in dict(endpoint=endpoint, page_size=page_size, referer_path=referer_path, map=map, fq=fq, O=O).items() if v not in (None, "")}
    products = await service.scrape_vtex_rest_deep(qs)
    if persist and products:
        await service.save_products(products)
    return [p.model_dump() for p in products]

