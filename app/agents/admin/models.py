"""
Shared constants and configuration for the finance bot.
No DB or I/O dependencies.
"""
from pathlib import Path
from zoneinfo import ZoneInfo

# Absolute project root, derived from this file's location:
#   models.py  →  app/agents/admin/  →  app/agents/  →  app/  →  project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent

STORAGE_DIR = PROJECT_ROOT / "storage"
REPORTS_DIR = PROJECT_ROOT / "reports"

DB_PATH = STORAGE_DIR / "admin.sqlite"
DEFAULT_CURRENCY = "CAD"

USERS = {
    "cross": "Cross",
    "pau": "Pau",
}

# Budgets compartidos del hogar (sin cambiar schema budgets).
# La tabla sigue siendo (user_id, category), pero el producto trata esas filas como UNA sola
# bolsa por categoría para todo el hogar. Convención: leer/escribir siempre el user_id de
# SHARED_BUDGET_OWNER_DISPLAY_NAME (histórico: en producción los budgets viven bajo "Pau").
# El % usado y el gasto vs tope usan EGRESO agregado de todos los usuarios en transactions.
#
# Duplicados legacy: si existieran filas para la misma categoría bajo Cross y bajo Pau, esta
# implementación solo ve las del owner canónico; las del otro usuario quedarían huérfanas
# hasta consolidarlas a mano (DELETE/INSERT o copia SQL), sin migración automática destructiva.
SHARED_BUDGET_OWNER_DISPLAY_NAME = USERS["pau"]

# Bot timezone (PST/PDT)
TZ = ZoneInfo("America/Los_Angeles")

# Telegram username -> internal user key
USER_MAP = {
    "cruz170t": "cross",
}

DEFAULT_USER = "cross"

# Canónico visible; LEGACY_* es el nombre previo en DB hasta migración manual SQL.
SUBSCRIPCIONES_OTROS = "SUBSCRIPCIONES / OTROS"
LEGACY_SUBSCRIPCIONES_OTROS = "SUSCRIPCIONES / OTROS"


def category_db_variants(canonical_category: str) -> tuple[str, ...]:
    """
    Valores de category en SQLite a considerar para una categoría canónica.
    Incluye el nombre legacy de subscripciones hasta unificar datos en producción.
    """
    if canonical_category == SUBSCRIPCIONES_OTROS:
        return (SUBSCRIPCIONES_OTROS, LEGACY_SUBSCRIPCIONES_OTROS)
    return (canonical_category,)


CATEGORIES = [
    "INGRESOS",
    "HOGAR",
    "COMIDA/SUPER",
    "TRANSPORTE",
    "SALUD Y BIENESTAR",
    "ROPA Y BELLEZA",
    "DIVERSIÓN Y SALIDAS",
    "EDUCACIÓN",
    SUBSCRIPCIONES_OTROS,
    "VARIOS / IMPREVISTOS",
    "AHORROS",
]

# Income categories (new; INGRESOS is legacy, kept for old data)
INCOME_CATEGORIES = [
    "SALARIO",
    "FREELANCE",
    "NEGOCIO",
    "INVERSIONES",
    "REEMBOLSO",
    "REGALOS",
    "OTROS INGRESOS",
]

# Aliases for income category detection. Order matters: more specific first.
INCOME_CATEGORY_ALIASES = {
    "me regalaron": "REGALOS",
    "regalo recibido": "REGALOS",
    "dividendos": "INVERSIONES",
    "intereses": "INVERSIONES",
    "rendimientos": "INVERSIONES",
    "inversiones": "INVERSIONES",
    "inversion": "INVERSIONES",
    "inversión": "INVERSIONES",
    "reembolso": "REEMBOLSO",
    "devolucion": "REEMBOLSO",
    "devolución": "REEMBOLSO",
    "refund": "REEMBOLSO",
    "proyecto freelance": "FREELANCE",
    "freelancing": "FREELANCE",
    "freelance": "FREELANCE",
    "negocio propio": "NEGOCIO",
    "ventas": "NEGOCIO",
    "venta": "NEGOCIO",
    "negocio": "NEGOCIO",
    "payroll": "SALARIO",
    "salary": "SALARIO",
    "nómina": "SALARIO",
    "nomina": "SALARIO",
    "sueldo": "SALARIO",
    "salario": "SALARIO",
    "cobro": "OTROS INGRESOS",
    "pago recibido": "OTROS INGRESOS",
    "depósito": "OTROS INGRESOS",
    "deposito": "OTROS INGRESOS",
    "me depositaron": "OTROS INGRESOS",
    "me pagaron": "OTROS INGRESOS",
    "ingreso": "OTROS INGRESOS",
}

# Hints to detect income intent (centralized source of truth)
INCOME_HINTS = frozenset({
    "ingreso",
    "salario",
    "sueldo",
    "me pagaron",
    "me depositaron",
    "deposito",
    "depósito",
    "freelance",
    "reembolso",
    "me regalaron",
    "inversion",
    "inversión",
    "dividendos",
    "intereses",
    "rendimientos",
    "pago recibido",
    "cobro",
})

# Categories that cannot have budgets (income categories + legacy INGRESOS)
BUDGET_BLOCKED_CATEGORIES = frozenset(INCOME_CATEGORIES) | {"INGRESOS"}

CATEGORY_ALIASES = {
    "hogar": "HOGAR",
    "casa": "HOGAR",
    "renta": "HOGAR",
    "comida": "COMIDA/SUPER",
    "super": "COMIDA/SUPER",
    "supermercado": "COMIDA/SUPER",
    "uber": "TRANSPORTE",
    "taxi": "TRANSPORTE",
    "transporte": "TRANSPORTE",
    "doctor": "SALUD Y BIENESTAR",
    "farmacia": "SALUD Y BIENESTAR",
    "salud": "SALUD Y BIENESTAR",
    "ropa": "ROPA Y BELLEZA",
    "belleza": "ROPA Y BELLEZA",
    "salida": "DIVERSIÓN Y SALIDAS",
    "cine": "DIVERSIÓN Y SALIDAS",
    "diversion": "DIVERSIÓN Y SALIDAS",
    "curso": "EDUCACIÓN",
    "educacion": "EDUCACIÓN",
    "subscripciones": SUBSCRIPCIONES_OTROS,
    "subscripcion": SUBSCRIPCIONES_OTROS,
    "suscripciones": SUBSCRIPCIONES_OTROS,
    "suscripcion": SUBSCRIPCIONES_OTROS,
    "netflix": SUBSCRIPCIONES_OTROS,
    "imprevisto": "VARIOS / IMPREVISTOS",
    "varios": "VARIOS / IMPREVISTOS",
    "ahorro": "AHORROS",
}

TEMPLATE_PATH = PROJECT_ROOT / "app" / "templates" / "Plantilla_Presupuesto_Dashboard_SIMPLE.xlsx"

EXPORT_HEADERS = [
    "FECHA",
    "DESCRIPCIÓN",
    "CATEGORIA",
    "MÉTODO DE PAGO",
    "TIPO",
    "USUARIO",
    "MONTO",
]
