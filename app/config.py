from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    APP_NAME: str = " Scraper API"
    BASE_URL: str = "https://www.eurosupermercados.com.co"
    START_PATH: str = ""

    VTEX_PAGE_SIZE: int = 50
    VTEX_MODE: str = "rest"  # rest | graphql
    EURO_ENDPOINT_DEFAULT: str = "/api/catalog_system/pub/products/search/mercado"

    # --- PostgreSQL ---
    PG_DSN: str | None = "postgresql://postgres:sena2009QoMa@127.0.0.1:5432/postgres"
    PG_HOST: str = "127.0.0.1"
    PG_PORT: int = 5432
    PG_USER: str = "postgres"
    PG_PASSWORD: str = "sena2009QoMa"
    PG_DATABASE: str = "postgres"
    PG_SCHEMA: str = "public"
    PG_TABLE: str = "productos_euro"


    # HTTP
    USER_AGENT: str = "EUROScraper/1.0 (marendonq@gmail.com)"
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