import re
import html
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

def normalize_whitespace(text: str | None) -> str | None:
    if not text:
        return None
    return re.sub(r"\s+", " ", text).strip() or None

_TAG_RE = re.compile(r"<[^>]+>")

def html_to_text(s: str | None) -> str | None:
    """Desescapa HTML y quita tags básicos (<p>, <ul>, etc.)."""
    if not s:
        return None
    unescaped = html.unescape(s)
    no_tags = _TAG_RE.sub(" ", unescaped)
    return normalize_whitespace(no_tags)

def slugify(s: str | None) -> str | None:
    if not s:
        return None
    s = s.strip().lower()
    s = re.sub(r"[^\w\s-]", "", s, flags=re.UNICODE)
    s = re.sub(r"\s+", "-", s)
    s = re.sub(r"-{2,}", "-", s)
    return s.strip("-") or None

def truncate(s: str | None, max_len: int) -> str | None:
    if s is None:
        return None
    s = str(s)
    return s[:max_len] if len(s) > max_len else s

def coerce_str_id(val, max_len: int) -> str | None:
    if val is None:
        return None
    s = str(val).strip()
    if not s:
        return None
    return s[:max_len]

def to_decimal_price(val) -> Optional[Decimal]:
    """Convierte a Decimal y cuantiza a 2 decimales. Acepta int/float/str."""
    if val is None:
        return None
    try:
        s = str(val).replace(",", "").strip()
        d = Decimal(s)
        return d.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except Exception:
        return None

import re
import unicodedata

def _strip_accents(s: str) -> str:
    return ''.join(c for c in unicodedata.normalize('NFD', s) if unicodedata.category(c) != 'Mn')

# 1) Prioridad: empaques/presentación > medidas
ORDERED = [
    # Empaques (más descriptivos primero)
    "CAJA","CAJAS","CJ","CAJ","BOX","CAJON","CAJONES","CRATE",
    "SET","KIT","KITS","JUEGO","JUEGOS","JGO",
    "BLISTER","BLIST","BLISTERS","BLT",
    "PAQUETE","PAQUETES","PAQ","PAQ.","PQT","PACK","MULTIPACK","DUOPACK","TRIPACK",
    "BOLSA","BOLSAS","BOL","BAG",
    "SOBRE","SOBRES","SOB","SACHET","SACHETS",
    "DISPLAY","DISPLAYS","EXHIBIDOR",
    "ESTUCHE","ESTUCHES","EST",
    "ROLLO","ROLLOS","RLL",
    "BOBINA","BOBINAS","CARRETE","CARRETES","BOB","CARRET","SPOOL","SPOOLS",
    "TIRA","TIRAS","TIR","TIR.",
    "TUBO","TUBOS",
    "FRASCO","FRASCOS",
    "BOTELLA","BOTELLAS","BOT",
    "TARRO","TARROS",
    "LATA","LATAS",
    "BALDE","BALDES","CUBETA","CUBETAS","CUBO","CUBOS","CANECA","CANECAS","CUÑETE","CUNETE","CUÑETES","TAMBOR","TAMBORES",
    "BIDON","BIDONES","GARRAFA","GARRAFAS",
    "JABA","JABAS","CANASTA","CANASTAS",
    "SACO","SACOS","BULTO","BULTOS","FARDO","FARDOS",
    "PAR","PARES",
    "PZA","PZ","PIEZA","PIEZAS","PCS","UND","UN","U","UNID","UNIDS","UNIDAD","UNIDADES",
    "RECAMBIO","RECARGA","RECARGAS","REPUESTO","REPUESTOS","CARTUCHO","CARTUCHOS","DISPENSADOR",
    # Medidas (peso/volumen/longitud/área/vol)
    "DOCENA","DZA","DZN","DZ",
    "KG","KGS","KILO","KILOS",
    "G","GR","GRAMO","GRAMOS","MG",
    "LB","LBS","LIBRA","LIBRAS","OZ","ONZA","ONZAS",
    "L","LT","LTS","LITRO","LITROS","ML","CC","GAL","GALON","GALONES","QT","PT",
    "M","MT","MTS","METRO","METROS","CM","MM",
    "M2","M^2","M²","CM2","CM^2","CM²","MM2","MM^2","MM²",
    "M3","M^3","M³","CM3","CM^3","CM³","MM3","MM^3","MM³",
]

# 2) Devolver una forma canónica
ALIAS_CANON = {
    # Empaques
    "CAJA":"CAJA","CAJAS":"CAJA","CJ":"CAJA","CAJ":"CAJA","BOX":"CAJA","CAJON":"CAJA","CAJONES":"CAJA","CRATE":"CAJA",
    "SET":"SET","KITS":"SET","KIT":"SET","JUEGO":"SET","JUEGOS":"SET","JGO":"SET",
    "BLISTER":"BLISTER","BLIST":"BLISTER","BLISTERS":"BLISTER","BLT":"BLISTER",
    "PAQUETE":"PAQUETE","PAQUETES":"PAQUETE","PAQ":"PAQUETE","PAQ.":"PAQUETE","PQT":"PAQUETE","PACK":"PAQUETE","MULTIPACK":"PAQUETE","DUOPACK":"PAQUETE","TRIPACK":"PAQUETE",
    "BOLSA":"BOLSA","BOLSAS":"BOLSA","BOL":"BOLSA","BAG":"BOLSA",
    "SOBRE":"SOBRE","SOBRES":"SOBRE","SOB":"SOBRE","SACHET":"SOBRE","SACHETS":"SOBRE",
    "DISPLAY":"DISPLAY","DISPLAYS":"DISPLAY","EXHIBIDOR":"DISPLAY",
    "ESTUCHE":"ESTUCHE","ESTUCHES":"ESTUCHE","EST":"ESTUCHE",
    "ROLLO":"ROLLO","ROLLOS":"ROLLO","RLL":"ROLLO",
    "BOBINA":"BOBINA","BOBINAS":"BOBINA","BOB":"BOBINA",
    "CARRETE":"CARRETE","CARRETES":"CARRETE","CARRET":"CARRETE","SPOOL":"CARRETE","SPOOLS":"CARRETE",
    "TIRA":"TIRA","TIRAS":"TIRA","TIR":"TIRA","TIR.":"TIRA",
    "TUBO":"TUBO","TUBOS":"TUBO",
    "FRASCO":"FRASCO","FRASCOS":"FRASCO",
    "BOTELLA":"BOTELLA","BOTELLAS":"BOTELLA","BOT":"BOTELLA",
    "TARRO":"TARRO","TARROS":"TARRO",
    "LATA":"LATA","LATAS":"LATA",
    "BALDE":"BALDE","BALDES":"BALDE","CUBETA":"CUBETA","CUBETAS":"CUBETA","CUBO":"CUBO","CUBOS":"CUBO",
    "CANECA":"CANECA","CANECAS":"CANECA","CUÑETE":"CUNETE","CUNETE":"CUNETE","CUÑETES":"CUNETE","TAMBOR":"TAMBOR","TAMBORES":"TAMBOR",
    "BIDON":"BIDON","BIDONES":"BIDON","GARRAFA":"GARRAFA","GARRAFAS":"GARRAFA",
    "JABA":"JABA","JABAS":"JABA","CANASTA":"CANASTA","CANASTAS":"CANASTA",
    "SACO":"SACO","SACOS":"SACO","BULTO":"BULTO","BULTOS":"BULTO","FARDO":"FARDO","FARDOS":"FARDO",
    "PAR":"PAR","PARES":"PAR",
    "PZA":"UNIDAD","PZ":"UNIDAD","PIEZA":"UNIDAD","PIEZAS":"UNIDAD","PCS":"UNIDAD","UND":"UNIDAD","UN":"UNIDAD","U":"UNIDAD","UNID":"UNIDAD","UNIDS":"UNIDAD","UNIDAD":"UNIDAD","UNIDADES":"UNIDAD",
    "RECAMBIO":"RECAMBIO","RECARGA":"RECARGA","RECARGAS":"RECARGA","REPUESTO":"REPUESTO","REPUESTOS":"REPUESTO","CARTUCHO":"CARTUCHO","CARTUCHOS":"CARTUCHO","DISPENSADOR":"DISPENSADOR",
    # Medidas
    "DOCENA":"DOCENA","DZA":"DOCENA","DZN":"DOCENA","DZ":"DOCENA",
    "KG":"KG","KGS":"KG","KILO":"KG","KILOS":"KG",
    "G":"G","GR":"G","GRAMO":"G","GRAMOS":"G","MG":"MG",
    "LB":"LB","LBS":"LB","LIBRA":"LB","LIBRAS":"LB","OZ":"OZ","ONZA":"OZ","ONZAS":"OZ",
    "L":"L","LT":"L","LTS":"L","LITRO":"L","LITROS":"L","ML":"ML","CC":"ML","GAL":"GAL","GALON":"GAL","GALONES":"GAL","QT":"QT","PT":"PT",
    "M":"M","MT":"M","MTS":"M","METRO":"M","METROS":"M","CM":"CM","MM":"MM",
    "M2":"M2","M^2":"M2","M²":"M2","CM2":"CM2","CM^2":"CM2","CM²":"CM2","MM2":"MM2","MM^2":"MM2","MM²":"MM2",
    "M3":"M3","M^3":"M3","M³":"M3","CM3":"CC","CM^3":"CC","CM³":"CC","MM3":"MM3","MM^3":"MM3","MM³":"MM3",
}

def infer_unidad_from_title(title: str | None) -> str | None:
    if not title:
        return None
    # normaliza: quita acentos, mayúsculas y separa dígitos/letras tipo "500ML" -> "500 ML"
    s = _strip_accents(title).upper()
    s = re.sub(r"(\d)([A-Z])", r"\1 \2", s)
    s = re.sub(r"([A-Z])(\d)", r"\1 \2", s)
    tokens = re.split(r"[\s\-/_,.()]+", s)

    for t in ORDERED:
        if t in tokens:
            return ALIAS_CANON.get(t, t)
    return "UND"
