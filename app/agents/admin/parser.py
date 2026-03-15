"""
Parse free-text input into structured transaction data.
Extracts amount, category, payment method, and type (income/expense).
"""
import re
from typing import Optional

from app.agents.admin.models import CATEGORIES, CATEGORY_ALIASES


def normalize_category(input_text: str) -> Optional[str]:
    """
    Normaliza entrada de categoría a la categoría oficial del sistema.
    Retorna None si no hay coincidencia clara. No usa fallback.
    """
    t = input_text.lower().strip()
    if not t:
        return None
    for cat in CATEGORIES:
        if cat.lower() == t:
            return cat
    for key in CATEGORY_ALIASES:
        if key in t:
            return CATEGORY_ALIASES[key]
    return None


def detect_category(text: str) -> str:
    t = text.lower()
    for key in CATEGORY_ALIASES:
        if key in t:
            return CATEGORY_ALIASES[key]
    return "VARIOS / IMPREVISTOS"


def detect_payment(text: str) -> str:
    t = text.lower()
    if "credito" in t:
        return "TARJETA DE CREDITO"
    if "debito" in t:
        return "DEBITO"
    if "transfer" in t:
        return "TRANSFERENCIA"
    if "cash" in t or "efectivo" in t:
        return "CASH"
    return "DEBITO"


def extract_amount(text: str) -> Optional[float]:
    m = re.search(r"\d+(\.\d+)?", text)
    return float(m.group()) if m else None


def is_ingreso(text: str) -> bool:
    return "ingreso" in text.lower()
