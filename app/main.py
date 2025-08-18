from __future__ import annotations
from fastapi import FastAPI
from .config import settings
from .http.client import HttpClient
from .services.scraping_service import ScrapingService
from .api.routes import init_routes, router
from .storage.sqlite import SQLiteDb, SQLiteProductRepository, SQLiteCategoryRepository

http_client = HttpClient()
db = SQLiteDb()  # usa settings.DB_PATH

def build_app() -> FastAPI:
    app = FastAPI(title=settings.APP_NAME)

    product_repo = SQLiteProductRepository(db)
    category_repo = SQLiteCategoryRepository(db)

    service = ScrapingService(
        http=http_client,
        product_repo=product_repo,
        category_repo=category_repo,
        base_url=settings.BASE_URL,
        start_path=settings.START_PATH,
    )

    init_routes(service)

    @app.on_event("startup")
    async def _startup():
        app.state.http_lifespan = http_client.lifespan()
        await app.state.http_lifespan.__aenter__()
        app.state.db_lifespan = db.lifespan()
        await app.state.db_lifespan.__aenter__()

    @app.on_event("shutdown")
    async def _shutdown():
        await app.state.http_lifespan.__aexit__(None, None, None)
        await app.state.db_lifespan.__aexit__(None, None, None)

    app.include_router(router, prefix="")
    return app

app = build_app()
