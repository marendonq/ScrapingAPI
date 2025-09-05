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
    sku_id: Optional[Short12] = None
    product_id: Optional[Short12] = None
    nombre_producto: Optional[str] = None
    marca: Optional[Short64] = None
    categoria_comerciante_id: Optional[Short128]  = None
    categoria_id: Optional[Short12] = None
    nombre_categoria: Optional[Short128] = None
    unidad: Optional[Short12] = None
    precio: Optional[float] = None            
    tipo_precio: Optional[Short12] = None
    imagen: Optional[str] = None            #
    url_producto: Optional[str] = None                     

    # Soporte de navegación por UI
    categorias: List[Category] = Field(default_factory=list)
