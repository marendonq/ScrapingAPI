import re
from typing import Optional

def normalize_whitespace(text: str | None) -> str | None:
    if not text:
        return None
    return re.sub(r"\s+", " ", text).strip() or None

def to_float_price(txt: str | None) -> Optional[float]:
    """
    Convierte strings tipo 'COP $ 1.234.567,89' a 1234567.89.
    Ajusta a formato decimal con punto.
    """
    if not txt:
        return None
    clean = txt.replace("\xa0", " ").strip()
    clean = re.sub(r"[^0-9,.\s]", "", clean)
    # Si tiene coma decimal y puntos de miles
    if clean.count(",") == 1 and clean.count(".") >= 1:
        clean = clean.replace(".", "").replace(",", ".")
    else:
        clean = clean.replace(",", ".")
    try:
        return float(clean)
    except ValueError:
        return None
