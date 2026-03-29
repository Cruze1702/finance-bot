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

# Bot timezone (PST/PDT)
TZ = ZoneInfo("America/Los_Angeles")

# Telegram username -> internal user key
USER_MAP = {
    "cruz170t": "cross",
}

DEFAULT_USER = "cross"

CATEGORIES = [
    "INGRESOS",
    "HOGAR",
    "COMIDA/SUPER",
    "TRANSPORTE",
    "SALUD Y BIENESTAR",
    "ROPA Y BELLEZA",
    "DIVERSIÓN Y SALIDAS",
    "EDUCACIÓN",
    "SUSCRIPCIONES / OTROS",
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
    "suscripcion": "SUSCRIPCIONES / OTROS",
    "netflix": "SUSCRIPCIONES / OTROS",
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
