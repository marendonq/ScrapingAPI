# WEBSCRAPING\_API

Documentación técnica y guía de uso del servicio de scraping para **Casa Ferretera**. Este proyecto expone una API con FastAPI que recorre páginas de listado de productos, extrae datos estructurados (JSON‑LD), enriquece cada producto con su detalle, y persiste todo en **SQLite**.

---

## ✨ Características clave

* **API REST** con FastAPI (/health, /scrape, /products)
* **Scraping** basado en **JSON‑LD** (`ItemList`, `Product`) y *fallback* al DOM para breadcrumbs
* **Concurrencia** asíncrona controlada
* **Persistencia** en SQLite con *upsert* idempotente por `url_producto`
* **Modelo de dominio** tipado con Pydantic (Product, Category)
* **Configuración** centralizada vía `pydantic-settings` (prefijo `SCRAPER_`)
* **Categorización** jerárquica y relación `product_categories`

---

## 🧱 Arquitectura y módulos

```
WEBSCRAPING_API/
│
├── app/
│   ├── api/                 # Endpoints FastAPI
│   ├── domain/              # Modelos y contratos de repositorios
│   ├── http/                # Cliente HTTP (httpx)
│   ├── parsers/             # Parseo de JSON-LD y breadcrumbs
│   ├── services/            # Caso de uso de scraping
│   ├── storage/             # Implementaciones de repositorios (SQLite)
│   ├── utils/               # Utilidades de texto/HTML
│   ├── config.py            # Settings
│   ├── main.py              # App factory y wiring
│   └── .gitignore
│
└── data/
    └── app.db               # Base de datos SQLite (ruta por defecto)
```

### Flujo de alto nivel

1. **/scrape** → `ScrapingService.scrape_all()`
2. Descarga de páginas de listado y extracción de productos desde JSON‑LD
3. Enriquecimiento por detalle del producto: breadcrumbs → categorías; opcionalmente campos del Product JSON‑LD
4. *Upsert* de productos y vinculación con categorías en SQLite

---

## ⚙️ Configuración

Definida en `app/config.py` mediante `Settings`. Se puede sobreescribir por variables de entorno con prefijo **`SCRAPER_`** (ej. `SCRAPER_DB_PATH`).

* `APP_NAME`: nombre de la app (para FastAPI docs)
* `BASE_URL`: dominio inicial (p. ej. `https://www.casaferretera.com`)
* `START_PATH`: ruta de listado con `page=1`
* **DB**: `DB_PATH` → `data/app.db` por defecto
* **HTTP**: `USER_AGENT`, `HTTP2`, *timeouts*, *limits*, `FOLLOW_REDIRECTS`
* **Scraping**: `CONCURRENCY`, `PAGE_DELAY_SECS`, `MAX_PAGES`, `ENRICH_FROM_PRODUCT_DETAIL`

> Ejemplo: `SCRAPER_MAX_PAGES=3 uvicorn app.main:app --reload`

---

## 🔌 HTTP Client

`app/http/client.py` implementa un `httpx.AsyncClient` con *lifespan* propio, `User-Agent` configurable y límites de conexiones. `get_text(url)` devuelve el HTML y propaga errores HTTP.

---

## 🧠 Parsing (JSON‑LD y breadcrumbs)

`app/parsers/jsonld.py`:

* Extrae bloques `application/ld+json`
* **Productos** desde `ItemList.itemListElement[].item` (o `Product` único)
* Normaliza `name`, `description` (HTML → texto), `sku`, `brand`, `offers.price` y `priceCurrency`
* **Breadcrumbs**:

  * Intenta `BreadcrumbList` en JSON‑LD
  * *Fallback* a selectores del DOM (`div[data-testid="breadcrumb"] a...`)
* Genera *slugs* desde URL o `slugify(name)`

---

## 🗃️ Persistencia y esquema

**SQLite** con *migración* automática al iniciar la app.

Tablas principales:

* `categories(id, name, slug UNIQUE, url)` + índice por `slug`
* `products(id, nombre, descripcion, precio, divisa, url_producto UNIQUE, image_url, sku, brand, categoria, codigo_categoria)` + índices por `sku` y `codigo_categoria`
* `product_categories(product_id, category_id, level)` (PK compuesta)

**Upsert**: conflicto por `url_producto` actualiza campos no nulos del nuevo registro.

Ruta de la DB: si `DB_PATH` es relativa (p. ej. `data/app.db`), se resuelve al **root del proyecto** y se crean directorios si faltan.

---

## 🧩 Repositorios y dominio

* **Modelos** (`app/domain/models.py`): `Product`, `Category` (Pydantic), con URL tipadas y listas de categorías por producto.
* **Contratos** (`app/domain/repositories.py`): `ProductRepository`, `CategoryRepository` (Protocol) + implementaciones **InMemory** para pruebas.
* **SQLite** (`app/storage/sqlite.py`): `SQLiteDb` (con *lifespan*, PRAGMAs, migración) y repos `SQLiteProductRepository` / `SQLiteCategoryRepository`.

  * `ensure_path(crumbs)` crea/actualiza categorías por `slug` y retorna objetos con `id`
  * `save_many(products)` hace *upsert* y re‑asigna enlaces `product_categories` con niveles `level` en orden de breadcrumb

---

## 🧪 Servicio de scraping

`app/services/scraping_service.py`:

* `_page_url(page)` sustituye `page=...` en `START_PATH`
* `_fetch_list_page(page)` → `parse_itemlist_products` → `Product` básicos
* `_enrich_from_detail(products)` descarga detalle concurrente (semáforo = `CONCURRENCY`), obtiene breadcrumbs → categorías (y opcionalmente `descripcion`, `image_url`, `sku`, `brand` desde `Product` del detalle)
* `scrape_all()` pagina hasta agotar o `MAX_PAGES`, aplica `PAGE_DELAY_SECS`, enriquece, asigna `id` temporales y persiste todo
* `list_products()` retorna los productos desde la DB

---

## 🌐 API HTTP

**Montaje**: `app/main.py` crea la app, configura *lifespans* de HTTP y DB, y registra rutas.

Rutas (`app/api/routes.py`):

* `GET /health` → `{ "ok": true }`
* `POST /scrape` → `List[Product]` (ejecuta scraping completo)
* `GET /products` → `List[Product]` (lee desde SQLite)

**Ejemplos**

```bash
# Iniciar
uvicorn app.main:app --reload

# Salud
curl http://127.0.0.1:8000/health

# Ejecutar scraping (puede tardar según MAX_PAGES / red)
curl -X POST http://127.0.0.1:8000/scrape | jq '.'

# Consultar productos
curl http://127.0.0.1:8000/products | jq '.'
```

---

## 🧰 Utilidades

`app/utils/text.py`:

* `normalize_whitespace` (limpieza), `html_to_text` (desescape + strip tags), `to_float_price` (normaliza precio), `slugify` (para slugs estables)

---

## 🚀 Puesta en marcha

1. **Python 3.11+** recomendado
2. Crear entorno y deps (ejemplo):

   ```bash
   python -m venv .venv && source .venv/bin/activate  # Windows: .venv\Scripts\activate
   pip install fastapi uvicorn[standard] httpx selectolax pydantic pydantic-settings aiosqlite
   ```
3. Variables opcionales (ejemplos):

   ```bash
   export SCRAPER_MAX_PAGES=2
   export SCRAPER_CONCURRENCY=8
   export SCRAPER_DB_PATH=data/app.db
   ```
4. Iniciar API: `uvicorn app.main:app --reload`

La primera ejecución creará la base de datos y tablas si no existen.

---

## 🧯 Errores comunes y resolución

* **"HttpClient not initialized" / "SQLiteDb not initialized"**: invocar siempre dentro del ciclo de vida de la app (la `main.py` ya lo hace). Evita usar los clientes fuera del *lifespan*.
* **Bloqueos de sitio**: ajustar `USER_AGENT`, `CONCURRENCY`, `PAGE_DELAY_SECS`. Considerar *retry/backoff* si el sitio limita tráfico.
* **Cambios de marca/DOM**: actualizar selectores de fallback o parseo de JSON‑LD.
