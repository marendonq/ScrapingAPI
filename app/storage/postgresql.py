# app/storage/postgres.py
from __future__ import annotations
import asyncpg
from contextlib import asynccontextmanager
from typing import List, Iterable, Optional
from decimal import Decimal

from ..config import settings
from ..domain.models import Product
from ..domain.repositories import ProductRepository, NoopCategoryRepository

def _build_dsn() -> str:
    if settings.PG_DSN:
        return settings.PG_DSN
    return (
        f"postgresql://{settings.PG_USER}:{settings.PG_PASSWORD}"
        f"@{settings.PG_HOST}:{settings.PG_PORT}/{settings.PG_DATABASE}"
    )

class PgDb:
    def __init__(self) -> None:
        self._pool: Optional[asyncpg.Pool] = None

    @asynccontextmanager
    async def lifespan(self):
        self._pool = await asyncpg.create_pool(dsn=_build_dsn(), min_size=1, max_size=10)
        try:
            yield self
        finally:
            await self._pool.close()  # type: ignore

    @property
    def pool(self) -> asyncpg.Pool:
        if self._pool is None:
            raise RuntimeError("PgDb not initialized. Use within lifespan().")
        return self._pool

# ---------- REPO de Productos en PostgreSQL ----------
class PgProductRepository(ProductRepository):
    def __init__(self, db: PgDb) -> None:
        self.db = db
        self.schema = settings.PG_SCHEMA
        self.table = settings.PG_TABLE

    async def ensure_schema(self) -> None:
        ddl = f"""
        CREATE SCHEMA IF NOT EXISTS {self.schema};

        CREATE TABLE IF NOT EXISTS {self.schema}.{self.table} (
            sku_id TEXT PRIMARY KEY,
            product_id TEXT NULL,
            nombre_producto TEXT NOT NULL,
            marca TEXT NULL,
            categoria_comerciante TEXT NULL,
            categoria_id TEXT NULL,
            nombre_categoria TEXT NULL,
            unidad TEXT NULL,
            precio MONEY NULL,
            tipo_precio TEXT NULL,
            imagen TEXT NULL,
            url_producto TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_{self.table}_categoria ON {self.schema}.{self.table}(categoria_id);
        CREATE INDEX IF NOT EXISTS idx_{self.table}_marca ON {self.schema}.{self.table}(marca);
        """
        async with self.db.pool.acquire() as conn:
            async with conn.transaction():
                for stmt in [s for s in ddl.split(";") if s.strip()]:
                    await conn.execute(stmt + ";")


    async def save_many(self, products: list[Product]) -> None:
        if not products:
            return
        cols = (
            "sku_id, product_id, nombre_producto, marca, "
            "categoria_comerciante, categoria_id, nombre_categoria, "
            "unidad, precio, tipo_precio, imagen, url_producto"
        )
        # Usamos cast a numeric -> money en el INSERT
        sql = f"""
        INSERT INTO {self.schema}.{self.table}
            ({cols})
        VALUES
            ($1, $2, $3, $4, $5, $6, $7, $8, $9::numeric::money, $10, $11, $12)
        ON CONFLICT (sku_id) DO UPDATE SET
            product_id = COALESCE(EXCLUDED.product_id, {self.table}.product_id),
            nombre_producto = EXCLUDED.nombre_producto,
            marca = COALESCE(EXCLUDED.marca, {self.table}.marca),
            categoria_comerciante = COALESCE(EXCLUDED.categoria_comerciante, {self.table}.categoria_comerciante),
            categoria_id = COALESCE(EXCLUDED.categoria_id, {self.table}.categoria_id),
            nombre_categoria = COALESCE(EXCLUDED.nombre_categoria, {self.table}.nombre_categoria),
            unidad = COALESCE(EXCLUDED.unidad, {self.table}.unidad),
            precio = COALESCE(EXCLUDED.precio, {self.table}.precio),
            tipo_precio = COALESCE(EXCLUDED.tipo_precio, {self.table}.tipo_precio),
            imagen = COALESCE(EXCLUDED.imagen, {self.table}.imagen),
            url_producto = COALESCE(EXCLUDED.url_producto, {self.table}.url_producto)
        ;
        """
        async with self.db.pool.acquire() as conn:
            async with conn.transaction():
                for p in products:
                    precio_num = None if p.precio is None else Decimal(p.precio)  # numeric
                    await conn.execute(
                        sql,
                        p.sku_id,
                        p.product_id,
                        p.nombre_producto,
                        p.marca,
                        p.categoria_comerciante_id,
                        p.categoria_id,
                        p.nombre_categoria,
                        p.unidad,
                        precio_num,
                        p.tipo_precio,
                        (str(p.imagen) if p.imagen else None),
                        str(p.url_producto),
                    )

    async def list_all(self) -> list[Product]:
        sql = f"""
        SELECT
            sku_id, product_id, nombre_producto, marca,
            categoria_comerciante, categoria_id, nombre_categoria,
            unidad, (precio::numeric) AS precio_num, tipo_precio, imagen, url_producto
        FROM {self.schema}.{self.table}
        ORDER BY sku_id;
        """
        async with self.db.pool.acquire() as conn:
            rows = await conn.fetch(sql)

        out: List[Product] = []
        for r in rows:
            out.append(
                Product(
                    sku_id=r["sku_id"],
                    product_id=r["product_id"],
                    nombre_producto=r["nombre_producto"],
                    marca=r["marca"],
                    categoria_comerciante_id=r["categoria_comerciante"],
                    categoria_id=r["categoria_id"],
                    nombre_categoria=r["nombre_categoria"],
                    unidad=r["unidad"],
                    precio=(None if r["precio_num"] is None else float(r["precio_num"])),
                    tipo_precio=r["tipo_precio"],
                    imagen=r["imagen"],
                    url_producto=r["url_producto"],
                    categorias=[],
                )
            )
        return out
