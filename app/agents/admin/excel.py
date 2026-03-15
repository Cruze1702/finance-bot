"""
Excel report generation (monthly transactions).
Two modes: clean export and template-based export.
"""
import shutil
from datetime import datetime
from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.styles import PatternFill

from app.agents.admin.models import EXPORT_HEADERS, REPORTS_DIR, TEMPLATE_PATH
from app.agents.admin.repositories import (
    get_conn,
    get_all_users,
    get_budgets,
    get_expense_by_category_for_month,
)
from app.agents.admin import stats

FILL_EGRESO = PatternFill(fill_type="solid", fgColor="FFEBEE")
FILL_INGRESO = PatternFill(fill_type="solid", fgColor="E8F5E9")

CURRENCY_FORMAT = '"$"#,##0.00'


def _current_month() -> str:
    return datetime.now().strftime("%Y-%m")


def _get_excel_summary_data(month_prefix: str) -> dict:
    """
    Datos para la hoja RESUMEN: mes, ingresos, gastos, balance,
    top 5 categorías, presupuestos por usuario.
    Reutiliza stats.compute_stats_all y repositories.
    """
    st = stats.compute_stats_all(month_prefix)
    start, end = stats.month_range(month_prefix)

    conn = get_conn()
    budget_rows = []
    try:
        for user_id, user_name in get_all_users(conn):
            rows = get_budgets(conn, user_id)
            expenses = get_expense_by_category_for_month(conn, user_id, start, end)
            for cat, budget_amt, curr in rows:
                budget_amt = float(budget_amt)
                if budget_amt <= 0:
                    continue
                spent = expenses.get(cat, 0.0)
                available = budget_amt - spent
                pct = (spent / budget_amt * 100.0)
                budget_rows.append({
                    "user": user_name,
                    "category": cat,
                    "budget": budget_amt,
                    "spent": spent,
                    "available": available,
                    "pct": round(pct, 1),
                    "currency": curr or "CAD",
                })
    finally:
        conn.close()

    return {
        "month": month_prefix,
        "income": st["income"],
        "expense": st["expense"],
        "balance": st["balance"],
        "top_categories": list(st["by_cat"].items())[:5],
        "budget_rows": budget_rows,
    }


def _build_resumen_sheet(wb, month_prefix: str) -> None:
    """
    Crea la hoja RESUMEN al inicio del workbook.
    Incluye: mes, ingresos, gastos, balance, top 5 categorías, presupuestos.
    """
    data = _get_excel_summary_data(month_prefix)

    if "RESUMEN" in wb.sheetnames:
        ws = wb["RESUMEN"]
        ws.delete_rows(1, ws.max_row)
    else:
        ws = wb.create_sheet("RESUMEN", 0)

    row = 1
    ws.cell(row=row, column=1).value = f"Resumen ejecutivo | {data['month']}"
    row += 2

    ws.cell(row=row, column=1).value = "Mes"
    ws.cell(row=row, column=2).value = data["month"]
    row += 1
    ws.cell(row=row, column=1).value = "Ingresos"
    ws.cell(row=row, column=2).value = data["income"]
    ws.cell(row=row, column=2).number_format = CURRENCY_FORMAT
    row += 1
    ws.cell(row=row, column=1).value = "Gastos"
    ws.cell(row=row, column=2).value = data["expense"]
    ws.cell(row=row, column=2).number_format = CURRENCY_FORMAT
    row += 1
    ws.cell(row=row, column=1).value = "Balance"
    ws.cell(row=row, column=2).value = data["balance"]
    ws.cell(row=row, column=2).number_format = CURRENCY_FORMAT
    row += 2

    ws.cell(row=row, column=1).value = "Top 5 categorías de gasto"
    row += 1
    if data["top_categories"]:
        ws.cell(row=row, column=1).value = "Categoría"
        ws.cell(row=row, column=2).value = "Monto"
        row += 1
        for cat, amt in data["top_categories"]:
            ws.cell(row=row, column=1).value = cat
            ws.cell(row=row, column=2).value = amt
            ws.cell(row=row, column=2).number_format = CURRENCY_FORMAT
            row += 1
    else:
        ws.cell(row=row, column=1).value = "Sin gastos en el mes"
        row += 1
    row += 1

    if data["budget_rows"]:
        ws.cell(row=row, column=1).value = "Presupuestos"
        row += 1
        ws.cell(row=row, column=1).value = "Usuario"
        ws.cell(row=row, column=2).value = "Categoría"
        ws.cell(row=row, column=3).value = "Presupuesto"
        ws.cell(row=row, column=4).value = "Gastado"
        ws.cell(row=row, column=5).value = "Disponible"
        ws.cell(row=row, column=6).value = "% usado"
        row += 1
        for r in data["budget_rows"]:
            ws.cell(row=row, column=1).value = r["user"]
            ws.cell(row=row, column=2).value = r["category"]
            ws.cell(row=row, column=3).value = r["budget"]
            ws.cell(row=row, column=3).number_format = CURRENCY_FORMAT
            ws.cell(row=row, column=4).value = r["spent"]
            ws.cell(row=row, column=4).number_format = CURRENCY_FORMAT
            ws.cell(row=row, column=5).value = r["available"]
            ws.cell(row=row, column=5).number_format = CURRENCY_FORMAT
            ws.cell(row=row, column=6).value = f"{r['pct']}%"
            row += 1
    else:
        ws.cell(row=row, column=1).value = "Sin presupuestos definidos"


def export_movimientos_excel(month_yyyy_mm: str | None = None) -> Path:
    """
    Export limpio (sin plantilla) para que Excel NUNCA pida reparar.
    Devuelve el Path del archivo generado.
    """
    month_prefix = month_yyyy_mm or _current_month()
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT
            t.date,
            t.description,
            t.category,
            t.payment_method,
            t.type,
            u.name,
            t.amount
        FROM transactions t
        JOIN users u ON u.id = t.user_id
        WHERE t.ts LIKE ?
        ORDER BY t.date ASC, t.id ASC
        """,
        (f"{month_prefix}%",),
    )
    rows = cur.fetchall()
    conn.close()

    wb = Workbook()
    ws = wb.active
    ws.title = "MOVIMIENTOS"
    ws.append(EXPORT_HEADERS)
    for row in rows:
        ws.append(list(row))

    for r, row in enumerate(rows, start=2):
        tx_type = (row[4] or "").strip().upper()
        fill = FILL_INGRESO if tx_type == "INGRESO" else (FILL_EGRESO if tx_type == "EGRESO" else None)
        if fill:
            for c in range(1, len(EXPORT_HEADERS) + 1):
                ws.cell(row=r, column=c).fill = fill

    _build_resumen_sheet(wb, month_prefix)

    out_path = REPORTS_DIR / f"movimientos_{month_prefix}.xlsx"
    wb.save(out_path)
    print(f"✅ Movimientos generado (sin plantilla): {out_path}")
    return out_path


def export_excel_template_copy(month_yyyy_mm: str | None = None) -> Path | None:
    """
    Export basado en plantilla.
    (Puede hacer que Excel pida 'reparar contenido' por validaciones/gráficos.)
    Devuelve el Path del archivo o None si la plantilla no existe.
    """
    if not TEMPLATE_PATH.exists():
        print("❌ Plantilla no encontrada")
        return None

    month_prefix = month_yyyy_mm or _current_month()
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = REPORTS_DIR / f"presupuesto_{month_prefix}.xlsx"
    shutil.copyfile(TEMPLATE_PATH, out_path)

    wb = load_workbook(out_path)
    if "MOVIMIENTOS" not in wb.sheetnames:
        ws = wb.create_sheet("MOVIMIENTOS")
    else:
        ws = wb["MOVIMIENTOS"]

    for i, h in enumerate(EXPORT_HEADERS, 1):
        ws.cell(row=1, column=i).value = h

    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT
            t.date,
            t.description,
            t.category,
            t.payment_method,
            t.type,
            u.name,
            t.amount
        FROM transactions t
        JOIN users u ON u.id = t.user_id
        WHERE t.ts LIKE ?
        ORDER BY t.date ASC, t.id ASC
        """,
        (f"{month_prefix}%",),
    )
    rows = cur.fetchall()
    conn.close()

    r = 2
    for row in rows:
        for c, val in enumerate(row, 1):
            ws.cell(row=r, column=c).value = val
        tx_type = (row[4] or "").strip().upper()
        fill = FILL_INGRESO if tx_type == "INGRESO" else (FILL_EGRESO if tx_type == "EGRESO" else None)
        if fill:
            for c in range(1, len(EXPORT_HEADERS) + 1):
                ws.cell(row=r, column=c).fill = fill
        r += 1

    _build_resumen_sheet(wb, month_prefix)

    wb.save(out_path)
    print(f"✅ Excel generado (plantilla): {out_path}")
    return out_path
