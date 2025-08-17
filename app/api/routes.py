from __future__ import annotations
from fastapi import APIRouter, HTTPException
from typing import List
from ..domain.models import Product
from ..services.scraping_service import ScrapingService

router = APIRouter()

# El servicio se inyectará desde main.py a través de dependencias.
service: ScrapingService | None = None

def init_routes(scraping_service: ScrapingService) -> APIRouter:
    global service
    service = scraping_service
    return router

@router.get("/health")
async def health():
    return {"ok": True}

@router.post("/scrape", response_model=List[Product])
async def run_scrape():
    if service is None:
        raise HTTPException(status_code=500, detail="Service not initialized")
    try:
        return await service.scrape_all()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/products", response_model=List[Product])
async def list_products():
    if service is None:
        raise HTTPException(status_code=500, detail="Service not initialized")
    return await service.list_products()
