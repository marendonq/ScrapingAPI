# app/storage/sqlite.py
from __future__ import annotations

from pathlib import Path
import aiosqlite
from contextlib import asynccontextmanager
from typing import Iterable, List
from decimal import Decimal

from ..domain.models import Product, Category
from ..domain.repositories import ProductRepository, NoopCategoryRepository
from ..utils.text import slugify, truncate
from ..config import settings

def _resolve_db_path(raw: str | None) -> str:
    default = "data/app.db"
    raw = (raw or default).strip()
    db_path = Path(raw)
    if not db_path.is_absolute():
        project_root = Path(__file__).resolve().parents[2]
        db_path = (project_root / db_path).resolve()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return str(db_path)

DEFAULT_DB_PATH = _resolve_db_path(getattr(settings, "DB_PATH", None))

class SQLiteDb:
    def __init__(self, db_path: str = DEFAULT_DB_PATH) -> None:
        effective = getattr(settings, "DB_PATH", db_path)
        self.db_path: str = _resolve_db_path(effective)
        self._conn: aiosqlite.Connection | None = None

    @asynccontextmanager
    async def lifespan(self):
        self._conn = await aiosqlite.connect(self.db_path)
        print(f"[SQLite] DB path: {self.db_path}")
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute("PRAGMA journal_mode=WAL;")
        await self._conn.execute("PRAGMA foreign_keys=ON;")
        await self._conn.execute("PRAGMA synchronous=NORMAL;")
        await self._conn.execute("PRAGMA temp_store=MEMORY;")
        await self._conn.execute("PRAGMA cache_size=-20000;")
        await self._conn.commit()
        await self._migrate()
        try:
            yield self
        finally:
            await self._conn.close()

    async def _migrate(self) -> None:
        assert self._conn is not None
        await self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS categories (
                id      INTEGER PRIMARY KEY AUTOINCREMENT,
                name    TEXT NOT NULL,
                slug    TEXT NOT NULL UNIQUE,
                url     TEXT
            );
            CREATE INDEX IF NOT EXISTS ix_categories_slug ON categories(slug);

            -- NUEVO esquema de products, alineado a la tabla de referencia
            CREATE TABLE IF NOT EXISTS products (
                id                    INTEGER PRIMARY KEY AUTOINCREMENT,
                sku_id                TEXT,         -- char(12)
                product_id            TEXT,         -- char(12)
                nombre_producto       TEXT NOT NULL,
                marca                 TEXT,         -- varchar(64)
                categoria_comerciante TEXT,         -- char(12)
                categoria_id          TEXT,         -- char(12)
                nombre_categoria      TEXT,         -- varchar(128)
                unidad                TEXT,         -- char(12)
                precio                TEXT,         -- guardamos Decimal como string cuantizada
                tipo_precio           TEXT,         -- char(12)
                imagen                TEXT,
                url_producto          TEXT NOT NULL UNIQUE
            );
            CREATE INDEX IF NOT EXISTS ix_products_sku_id ON products(sku_id);
            CREATE INDEX IF NOT EXISTS ix_products_categoria_id ON products(categoria_id);

            CREATE TABLE IF NOT EXISTS product_categories (
                product_id  INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
                category_id INTEGER NOT NULL REFERENCES categories(id) ON DELETE CASCADE,
                level       INTEGER NOT NULL,
                PRIMARY KEY (product_id, category_id)
            );
            """
        )
        await self._conn.commit()

    @property
    def conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("SQLiteDb not initialized. Use within lifespan().")
        return self._conn

    async def executemany(self, sql: str, seq_of_params: Iterable[tuple]) -> None:
        await self.conn.executemany(sql, seq_of_params)

    async def execute(self, sql: str, params: tuple = ()) -> aiosqlite.Cursor:
        return await self.conn.execute(sql, params)

    async def fetchone(self, sql: str, params: tuple = ()) -> aiosqlite.Row | None:
        cur = await self.conn.execute(sql, params)
        row = await cur.fetchone()
        await cur.close()
        return row

    async def fetchall(self, sql: str, params: tuple = ()) -> list[aiosqlite.Row]:
        cur = await self.conn.execute(sql, params)
        rows = await cur.fetchall()
        await cur.close()
        return list(rows)

# app/storage/sqlite.py
from ..utils.text import slugify  # asegúrate de tenerlo importado

class SQLiteCategoryRepository(NoopCategoryRepository):
    def __init__(self, db: SQLiteDb) -> None:
        self.db = db

    async def ensure_path(self, crumbs: list[dict]) -> list[Category]:
        out: list[Category] = []

        for c in (crumbs or []):
            name = (c.get("name") or "").strip()
            slug = c.get("slug") or slugify(name)  # fallback si no vino slug
            url  = c.get("url")

            # Si no hay slug ni con fallback, saltamos para no romper
            if not slug:
                continue

            # UPSERT atómico (evita UNIQUE constraint en concurrencia)
            await self.db.execute(
                """
                INSERT INTO categories(name, slug, url)
                VALUES(?, ?, ?)
                ON CONFLICT(slug) DO UPDATE SET
                    name=excluded.name,
                    url=COALESCE(categories.url, excluded.url)
                """,
                (name, slug, url),
            )

            # Leer la fila recién insertada/actualizada
            row = await self.db.fetchone(
                "SELECT id, name, slug, url FROM categories WHERE slug=?",
                (slug,),
            )

            # Si por alguna razón (muy raro) no aparece, comitea y reintenta una vez
            if row is None:
                await self.db.conn.commit()
                row = await self.db.fetchone(
                    "SELECT id, name, slug, url FROM categories WHERE slug=?",
                    (slug,),
                )
                if row is None:
                    # No nos caemos: solo seguimos con el resto
                    continue

            # aiosqlite.Row permite indexar por posición
            out.append(
                Category(id=int(row[0]), name=row[1], slug=row[2], url=row[3])
            )

        await self.db.conn.commit()
        return out


    async def list_all(self) -> list[Category]:
        rows = await self.db.fetchall("SELECT id, name, slug, url FROM categories ORDER BY id")
        return [Category(id=int(r[0]), name=r[1], slug=r[2], url=r[3]) for r in rows]

class SQLiteProductRepository(ProductRepository):
    def __init__(self, db: SQLiteDb) -> None:
        self.db = db

    async def save_many(self, products: list[Product]) -> None:
        await self.db.execute("BEGIN")
        try:
            for p in products:
                # precio (Decimal|None) -> str o None
                precio_str = str(p.precio) if p.precio is not None else None

                await self.db.execute(
                    """
                    INSERT INTO products (
                        sku_id, product_id, nombre_producto, marca,
                        categoria_comerciante, categoria_id, nombre_categoria,
                        unidad, precio, tipo_precio, imagen, url_producto
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(url_producto) DO UPDATE SET
                        sku_id=COALESCE(excluded.sku_id, products.sku_id),
                        product_id=COALESCE(excluded.product_id, products.product_id),
                        nombre_producto=excluded.nombre_producto,
                        marca=COALESCE(excluded.marca, products.marca),
                        categoria_comerciante=COALESCE(excluded.categoria_comerciante, products.categoria_comerciante),
                        categoria_id=COALESCE(excluded.categoria_id, products.categoria_id),
                        nombre_categoria=COALESCE(excluded.nombre_categoria, products.nombre_categoria),
                        unidad=COALESCE(excluded.unidad, products.unidad),
                        precio=COALESCE(excluded.precio, products.precio),
                        tipo_precio=COALESCE(excluded.tipo_precio, products.tipo_precio),
                        imagen=COALESCE(excluded.imagen, products.imagen)
                    ;
                    """,
                    (
                        p.sku_id,
                        p.product_id,
                        p.nombre_producto,
                        p.marca,
                        p.categoria_comerciante_id,
                        p.categoria_id,
                        p.nombre_categoria,
                        p.unidad,
                        precio_str,
                        p.tipo_precio,
                        (str(p.imagen) if p.imagen else None),
                        str(p.url_producto),
                    ),
                )
                row = await self.db.fetchone(
                    "SELECT id FROM products WHERE url_producto=?",
                    (str(p.url_producto),),
                )
                if row is None:
                    raise RuntimeError(f"No se encontró el producto recién upserted: {p.url_producto}")
                product_id = int(row[0])

                await self.db.execute(
                    "DELETE FROM product_categories WHERE product_id=?",
                    (product_id,),
                )
                for level, cat in enumerate(p.categorias):
                    if cat.id is None:
                        continue
                    await self.db.execute(
                        "INSERT OR IGNORE INTO product_categories(product_id, category_id, level) VALUES(?,?,?)",
                        (product_id, int(cat.id), level),
                    )
            await self.db.conn.commit()
        except Exception:
            await self.db.execute("ROLLBACK")
            raise

    async def list_all(self) -> list[Product]:
        rows = await self.db.fetchall(
            """
            SELECT id, sku_id, product_id, nombre_producto, marca,
                   categoria_comerciante, categoria_id, nombre_categoria,
                   unidad, precio, tipo_precio, imagen, url_producto
            FROM products
            ORDER BY id;
            """
        )
        links = await self.db.fetchall(
            """
            SELECT pc.product_id, c.id, c.name, c.slug, c.url, pc.level
            FROM product_categories pc
            JOIN categories c ON c.id = pc.category_id
            ORDER BY pc.product_id, pc.level;
            """
        )
        cats_by_pid: dict[int, list[Category]] = {}
        for pid, cid, name, slug, url, level in links:
            cats_by_pid.setdefault(int(pid), []).append(
                Category(id=int(cid), name=name, slug=slug, url=url)
            )

        out: List[Product] = []
        for r in rows:
            pid = int(r[0])
            precio = None if r[9] is None else Decimal(str(r[9]))
            out.append(
                Product(
                    sku_id=r[1],
                    product_id=r[0],
                    nombre_producto=r[3],
                    marca=r[4],
                    categoria_comerciante_id=r[5],
                    categoria_id=r[6],
                    nombre_categoria=r[7],
                    unidad=r[8],
                    precio=precio,
                    tipo_precio=r[10],
                    imagen=r[11],
                    url_producto=r[12],
                    categorias=cats_by_pid.get(pid, []),
                )
            )
        return out
