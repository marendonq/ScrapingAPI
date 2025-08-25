from __future__ import annotations
from decimal import Decimal
from typing import Annotated
from pydantic import BaseModel, AnyUrl, Field, HttpUrl, StringConstraints, ConfigDict, constr
from typing import List, Optional

class Category(BaseModel):
    id: int | None = Field(default=None)
    name: str
    slug: str | None = None
    url: AnyUrl | None = None
    parent_id: int = 0

Short12 = Annotated[str, StringConstraints(max_length=12)]
Short64 = Annotated[str, StringConstraints(max_length=64)]
Short128 = Annotated[str, StringConstraints(max_length=128)]

class Product(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)  # recorta espacios a todos los str

    id: int | None = Field(default=None)
    sku_id: Short12 | None = None
    product_id: Short12 | None = None
    nombre_producto: str
    marca: Short64 | None = None
    categoria_comerciante_id: Short128 | None = None
    categoria_id: Short12 | None = None
    nombre_categoria: Short128 | None = None
    unidad: Short12 | None = None
    precio: Decimal | None = None            
    tipo_precio: Short12 | None = None
    imagen: HttpUrl | None = None            #
    url_producto: AnyUrl                      

    # Soporte de navegación por UI
    categorias: List[Category] = Field(default_factory=list)
