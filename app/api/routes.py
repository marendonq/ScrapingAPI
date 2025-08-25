from __future__ import annotations
from fastapi import APIRouter, HTTPException, Depends
from typing import List
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

