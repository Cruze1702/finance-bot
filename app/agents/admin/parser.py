"""
Parse free-text input into structured transaction data.
Extracts amount, category, payment method, and type (income/expense).
"""
import re
from typing import Optional

from app.agents.admin.models import (
    CATEGORIES,
    CATEGORY_ALIASES,
    INCOME_CATEGORIES,
    INCOME_CATEGORY_ALIASES,
    INCOME_HINTS,
)


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
    """
    Detecta si el texto representa un ingreso.
    Prioridad: 1) prefijo "gasto " -> EGRESO  2) prefijo "ingreso " -> INGRESO
    3) hints de ingreso en texto -> INGRESO  4) else -> EGRESO
    """
    t = text.lower().strip()
    if t.startswith("gasto "):
        return False
    if t.startswith("ingreso "):
        return True
    for hint in INCOME_HINTS:
        if hint in t:
            return True
    return False


def detect_income_category(text: str) -> str:
    """
    Detecta categoría de ingreso a partir del texto.
    Solo debe llamarse cuando type == INGRESO.
    Fallback: OTROS INGRESOS.
    """
    t = text.lower()
    for alias, category in INCOME_CATEGORY_ALIASES.items():
        if alias in t:
            return category
    return "OTROS INGRESOS"


def resolve_income_category_for_input(input_text: str) -> Optional[str]:
    """
    Si el input es una categoría de ingreso (exacta o por alias), retorna esa categoría.
    Si no, retorna None. Usado para validar presupuestos.
    """
    t = input_text.lower().strip()
    if not t:
        return None
    if t == "ingresos":
        return "INGRESOS"
    for cat in INCOME_CATEGORIES:
        if cat.lower() == t:
            return cat
    for alias, cat in INCOME_CATEGORY_ALIASES.items():
        if alias in t or t in alias:
            return cat
    return None
