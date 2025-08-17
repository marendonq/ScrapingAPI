from __future__ import annotations
from fastapi import FastAPI
from .config import settings
from .http.client import HttpClient
from .services.scraping_service import ScrapingService
from .domain.repositories import InMemoryProductRepository, InMemoryCategoryRepository
from .api.routes import init_routes, router

http_client = HttpClient()

def build_app() -> FastAPI:
    app = FastAPI(title=settings.APP_NAME)

    product_repo = InMemoryProductRepository()
    category_repo = InMemoryCategoryRepository()

    service = ScrapingService(
        http=http_client,
        product_repo=product_repo,
        category_repo=category_repo,   # ← nuevo
        base_url=settings.BASE_URL,
        start_path=settings.START_PATH,
    )

    init_routes(service)

    @app.on_event("startup")
    async def _startup():
        app.state.http_lifespan = http_client.lifespan()
        await app.state.http_lifespan.__aenter__()

    @app.on_event("shutdown")
    async def _shutdown():
        await app.state.http_lifespan.__aexit__(None, None, None)

    app.include_router(router, prefix="")
    return app

app = build_app()
