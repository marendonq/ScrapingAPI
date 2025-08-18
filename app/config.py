from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    APP_NAME: str = "Casa Ferretera Scraper API"
    BASE_URL: str = "https://www.casaferretera.com"
    START_PATH: str = "/herramientas-y-maquinarias?page=1"

    # DB
    DB_PATH: str = "data/app.db"  

    # HTTP
    USER_AGENT: str = "CasaFerreteraScraper/1.0 (+contacto@example.com)"
    HTTP2: bool = True
    TIMEOUT_CONNECT: float = 5.0
    TIMEOUT_READ: float = 15.0
    TIMEOUT_WRITE: float = 10.0
    TIMEOUT_POOL: float = 10.0
    MAX_KEEPALIVE: int = 50
    MAX_CONNECTIONS: int = 100
    FOLLOW_REDIRECTS: bool = True

    # Scraping
    CONCURRENCY: int = 12
    PAGE_DELAY_SECS: float = 0.2
    MAX_PAGES: int | None = None
    ENRICH_FROM_PRODUCT_DETAIL: bool = True

    model_config = SettingsConfigDict(env_prefix="SCRAPER_")

settings = Settings()
