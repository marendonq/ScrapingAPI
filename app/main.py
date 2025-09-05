from __future__ import annotations
from fastapi import FastAPI
from .config import settings
from .http.client import HttpClient
from .services.scraping_service import ScrapingService
from .api.routes import init_routes, router
from .storage.postgresql import PgDb, PgProductRepository
from .domain.repositories import NoopCategoryRepository

http_client = HttpClient()
pg = PgDb()

def build_app() -> FastAPI:
    app = FastAPI(title=settings.APP_NAME)

    product_repo = PgProductRepository(pg)
    category_repo = NoopCategoryRepository()  

    service = ScrapingService(
        http=http_client,
        product_repo=product_repo,
        category_repo=category_repo,
        base_url=settings.BASE_URL,
        start_path=settings.START_PATH
    )

    init_routes(service)

    @app.on_event("startup")
    async def _startup():
        app.state.http_lifespan = http_client.lifespan()
        await app.state.http_lifespan.__aenter__()
        app.state.pg_lifespan = pg.lifespan()
        await app.state.pg_lifespan.__aenter__()
        product_repo = PgProductRepository(pg)
        await product_repo.ensure_schema()

    @app.on_event("shutdown")
    async def _shutdown():
        await app.state.http_lifespan.__aexit__(None, None, None)
        await app.state.pg_lifespan.__aexit__(None, None, None)

    app.include_router(router, prefix="")
    return app

app = build_app()
