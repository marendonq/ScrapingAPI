from __future__ import annotations
from fastapi import FastAPI
from .config import settings
from .http.client import HttpClient
from .parsers.casaferretera import CasaFerreteraListParser, CasaFerreteraDetailParser
from .services.scraping_service import ScrapingService
from .domain.repositories import InMemoryProductRepository
from .api.routes import init_routes, router

http_client = HttpClient()

def build_app() -> FastAPI:
    app = FastAPI(title=settings.APP_NAME)

    list_parser = CasaFerreteraListParser()
    detail_parser = CasaFerreteraDetailParser()
    repo = InMemoryProductRepository()

    service = ScrapingService(
        http=http_client,
        list_parser=list_parser,
        detail_parser=detail_parser,
        repo=repo,
        base_url=settings.BASE_URL,
        start_path=settings.START_PATH,
    )

    # Registrar rutas con la instancia del servicio
    init_routes(service)

    @app.on_event("startup")
    async def _startup():
        # Inicia el cliente HTTP
        app.state.http_lifespan = http_client.lifespan()
        await app.state.http_lifespan.__aenter__()

    @app.on_event("shutdown")
    async def _shutdown():
        await app.state.http_lifespan.__aexit__(None, None, None)

    # incluye el router ya inicializado
    app.include_router(router, prefix="")

    return app

app = build_app()
