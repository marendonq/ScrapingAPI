# app/storage/sqlite.py
from __future__ import annotations

from pathlib import Path
import aiosqlite
from contextlib import asynccontextmanager
from typing import Iterable, List

from ..domain.models import Product, Category
from ..domain.repositories import ProductRepository, CategoryRepository
from ..utils.text import slugify
from ..config import settings

# -------------------------
# Helpers de ruta
# -------------------------
def _resolve_db_path(raw: str | None) -> str:
    """
    Convierte DB_PATH a ruta absoluta y garantiza que el directorio exista.
    Si llega relativa (p.ej. 'data/app.db'), la anclamos a la raíz del repo.
    """
    default = "data/app.db"
    raw = (raw or default).strip()
    db_path = Path(raw)
    if not db_path.is_absolute():
        project_root = Path(__file__).resolve().parents[2]
        db_path = (project_root / db_path).resolve()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return str(db_path)

DEFAULT_DB_PATH = _resolve_db_path(getattr(settings, "DB_PATH", None))

# -------------------------
# Low-level DB helper
# -------------------------
class SQLiteDb:
    def __init__(self, db_path: str = DEFAULT_DB_PATH) -> None:
        effective = getattr(settings, "DB_PATH", db_path)
        self.db_path: str = _resolve_db_path(effective)
        self._conn: aiosqlite.Connection | None = None

    @asynccontextmanager
    async def lifespan(self):
        self._conn = await aiosqlite.connect(self.db_path)
        print(f"[SQLite] DB path: {self.db_path}")  # útil para verificar que miras el archivo correcto
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

            CREATE TABLE IF NOT EXISTS products (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre           TEXT NOT NULL,
                descripcion      TEXT,
                precio           REAL,
                divisa           TEXT,
                url_producto     TEXT NOT NULL UNIQUE,
                image_url        TEXT,
                sku              TEXT,
                brand            TEXT,
                categoria        TEXT,
                codigo_categoria TEXT
            );
            CREATE INDEX IF NOT EXISTS ix_products_sku ON products(sku);
            CREATE INDEX IF NOT EXISTS ix_products_categoria ON products(codigo_categoria);

            CREATE TABLE IF NOT EXISTS product_categories (
                product_id  INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
                category_id INTEGER NOT NULL REFERENCES categories(id) ON DELETE CASCADE,
                level       INTEGER NOT NULL,
                PRIMARY KEY (product_id, category_id)
            );
            """
        )
        await self._conn.commit()

    # Helpers
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

# -------------------------
# Category Repository (SQLite)
# -------------------------
class SQLiteCategoryRepository(CategoryRepository):
    def __init__(self, db: SQLiteDb) -> None:
        self.db = db

    async def ensure_path(self, crumbs: list[dict]) -> list[Category]:
        out: list[Category] = []
        changed = False
        for c in crumbs:
            name = (c.get("name") or "").strip()
            slug = c.get("slug") or slugify(name) or ""
            url  = c.get("url")
            if not slug:
                continue
            row = await self.db.fetchone(
                "SELECT id, name, slug, url FROM categories WHERE slug=?",
                (slug,),
            )
            if row is None:
                cur = await self.db.execute(
                    "INSERT INTO categories(name, slug, url) VALUES(?,?,?)",
                    (name, slug, url),
                )
                cat_id = cur.lastrowid
                if cat_id is None:
                    raise RuntimeError("No se obtuvo lastrowid al insertar categoría")
                out.append(Category(id=int(cat_id), name=name, slug=slug, url=url))
                changed = True
            else:
                cat = Category(id=int(row[0]), name=row[1], slug=row[2], url=row[3])
                updated = False
                if name and cat.name != name:
                    await self.db.execute("UPDATE categories SET name=? WHERE id=?", (name, cat.id))
                    updated = True
                if url and not cat.url:
                    await self.db.execute("UPDATE categories SET url=? WHERE id=?", (url, cat.id))
                    updated = True
                if updated:
                    changed = True
                out.append(cat)
        if changed:
            await self.db.conn.commit()
        return out

    async def list_all(self) -> list[Category]:
        rows = await self.db.fetchall("SELECT id, name, slug, url FROM categories ORDER BY id")
        return [Category(id=int(r[0]), name=r[1], slug=r[2], url=r[3]) for r in rows]

# -------------------------
# Product Repository (SQLite)
# -------------------------
class SQLiteProductRepository(ProductRepository):
    def __init__(self, db: SQLiteDb) -> None:
        self.db = db

    async def save_many(self, products: list[Product]) -> None:
        await self.db.execute("BEGIN")
        try:
            for p in products:
                await self.db.execute(
                    """
                    INSERT INTO products (nombre, descripcion, precio, divisa, url_producto,
                                          image_url, sku, brand, categoria, codigo_categoria)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(url_producto) DO UPDATE SET
                        nombre=excluded.nombre,
                        descripcion=COALESCE(excluded.descripcion, products.descripcion),
                        precio=COALESCE(excluded.precio, products.precio),
                        divisa=COALESCE(excluded.divisa, products.divisa),
                        image_url=COALESCE(excluded.image_url, products.image_url),
                        sku=COALESCE(excluded.sku, products.sku),
                        brand=COALESCE(excluded.brand, products.brand),
                        categoria=COALESCE(excluded.categoria, products.categoria),
                        codigo_categoria=COALESCE(excluded.codigo_categoria, products.codigo_categoria)
                    ;
                    """,
                    (
                        p.nombre,
                        p.descripcion,
                        p.precio,
                        p.divisa,
                        str(p.url_producto),
                        (str(p.image_url) if p.image_url else None),
                        p.sku,
                        p.brand,
                        p.categoria,
                        p.codigo_categoria,
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
            SELECT id, nombre, descripcion, precio, divisa, url_producto, image_url,
                   sku, brand, categoria, codigo_categoria
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
            out.append(
                Product(
                    id=pid,
                    nombre=r[1],
                    descripcion=r[2],
                    precio=r[3],
                    divisa=r[4],
                    url_producto=r[5],
                    image_url=r[6],
                    sku=r[7],
                    brand=r[8],
                    categorias=cats_by_pid.get(pid, []),
                    categoria=r[9],
                    codigo_categoria=r[10],
                )
            )
        return out
