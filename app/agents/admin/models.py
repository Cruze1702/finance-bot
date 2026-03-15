"""
Shared constants and configuration for the finance bot.
No DB or I/O dependencies.
"""
from pathlib import Path

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

PAYMENT_METHODS = [
    "TARJETA DE CREDITO",
    "DEBITO",
    "CASH",
    "TRANSFERENCIA",
]

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
