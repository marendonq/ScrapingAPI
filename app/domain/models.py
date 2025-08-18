from __future__ import annotations
from pydantic import BaseModel, AnyUrl, Field, HttpUrl
from typing import Optional, List

class Category(BaseModel):
    id: int | None = Field(default=None)
    name: str
    slug: str | None = None
    url: AnyUrl | None = None

class Product(BaseModel):
    id: int | None = Field(default=None)
    nombre: str
    descripcion: str | None = None
    precio: float | None = None
    divisa: str | None = None
    url_producto: AnyUrl
    image_url: HttpUrl | None = None
    sku: str | None = None
    brand: str | None = None
    categorias: List[Category] = Field(default_factory=list) 
    categoria: str | None = None                              
    codigo_categoria: str | None = None                       
