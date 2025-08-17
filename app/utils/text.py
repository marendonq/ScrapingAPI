import re
import html
from typing import Optional

def normalize_whitespace(text: str | None) -> str | None:
    if not text:
        return None
    return re.sub(r"\s+", " ", text).strip() or None

def to_float_price(val) -> Optional[float]:
    if val is None:
        return None
    try:
        # en JSON-LD ya viene número (ej. 467700); si viniera string, conviértelo
        return float(str(val).replace(",", "").strip())
    except (ValueError, TypeError):
        return None

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
