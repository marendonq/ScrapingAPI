from __future__ import annotations
from contextlib import asynccontextmanager
import httpx
from ..config import settings

class HttpClient:
    """
    Responsabilidad única: gestionar un cliente HTTP asíncrono con configuración centralizada.
    """
    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None

    @asynccontextmanager
    async def lifespan(self):
        self._client = httpx.AsyncClient(
            headers={"User-Agent": settings.USER_AGENT},
            http2=settings.HTTP2,
            timeout=httpx.Timeout(
                connect=settings.TIMEOUT_CONNECT,
                read=settings.TIMEOUT_READ,
                write=settings.TIMEOUT_WRITE,
                pool=settings.TIMEOUT_POOL,
            ),
            limits=httpx.Limits(
                max_keepalive_connections=settings.MAX_KEEPALIVE,
                max_connections=settings.MAX_CONNECTIONS,
            ),
            follow_redirects=settings.FOLLOW_REDIRECTS,
        )
        try:
            yield
        finally:
            await self._client.aclose()

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            raise RuntimeError("HttpClient not initialized. Use within lifespan().")
        return self._client

    async def get_text(self, url: str) -> str:
        resp = await self.client.get(url)
        resp.raise_for_status()
        return resp.text
