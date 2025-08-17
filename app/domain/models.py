from __future__ import annotations
from pydantic import BaseModel, AnyUrl, Field
from typing import Optional

class Product(BaseModel):
    """
    Entidad de dominio: Producto.
    """
    id: int | None = Field(default=None)             # asignado en el servicio
    nombre: str
    precio: float | None = None                      # normalizado en COP
    descripcion: str | None = None
    url_producto: AnyUrl
