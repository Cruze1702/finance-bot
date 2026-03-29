"""
Monthly statistics computation and formatting.
"""
import calendar
import re
from datetime import date, datetime
from typing import Any

from app.agents.admin.models import TZ
from app.agents.admin.repositories import (
    get_all_users,
    get_conn,
    get_budgets,
    get_expense_by_category_for_month,
    get_income_expense_for_date,
)


def month_range(month_yyyy_mm: str) -> tuple[str, str]:
    y, m = map(int, month_yyyy_mm.split("-"))
    start = date(y, m, 1)
    end = date(y + 1, 1, 1) if m == 12 else date(y, m + 1, 1)
    return start.isoformat(), end.isoformat()


def _days_for_daily_avg(month_yyyy_mm: str) -> int:
    """
    Días a usar para promedio diario: días transcurridos si es mes actual,
    total de días del mes si es mes pasado.
    """
    y, m = map(int, month_yyyy_mm.split("-"))
    today = datetime.now(TZ).date()
    if today.year == y and today.month == m:
        return today.day
    return calendar.monthrange(y, m)[1]


def prev_month(month_yyyy_mm: str) -> str:
    y, m = map(int, month_yyyy_mm.split("-"))
    if m == 1:
        return f"{y - 1:04d}-12"
    return f"{y:04d}-{m - 1:02d}"


def compute_stats(user_name: str, month_yyyy_mm: str) -> dict[str, Any]:
    """
    Estadísticas mensuales para un usuario.
    Filtra por user_id: ingresos y gastos son exclusivos de ese usuario.
    Misma estructura de retorno que usa telegram_bot (format_stats).
    """
    start, end = month_range(month_yyyy_mm)
    p = prev_month(month_yyyy_mm)
    pstart, pend = month_range(p)

    conn = get_conn()
    cur = conn.cursor()

    row = cur.execute("SELECT id FROM users WHERE lower(name)=lower(?)", (user_name,)).fetchone()
    if not row:
        conn.close()
        return {
            "month": month_yyyy_mm,
            "user": user_name,
            "income": 0.0,
            "expense": 0.0,
            "balance": 0.0,
            "by_cat": {},
            "prev_exp": 0.0,
        }

    user_id = row[0]

    rows = cur.execute(
        """
        SELECT date, type, amount, category
        FROM transactions
        WHERE user_id = ?
          AND date >= ?
          AND date < ?
        ORDER BY id ASC
        """,
        (user_id, start, end),
    ).fetchall()

    income = 0.0
    expense = 0.0
    by_cat = {}
    for r in rows:
        t = (r[1] or "").upper().strip()   # type
        a = float(r[2] or 0.0)             # amount
        cat = (r[3] or "SIN CATEGORIA").upper().strip()  # category
        if "INGRESO" in t:
            income += a
        else:
            expense += a
            by_cat[cat] = by_cat.get(cat, 0.0) + a

    prev_rows = cur.execute(
        """
        SELECT type, amount
        FROM transactions
        WHERE user_id = ?
          AND date >= ?
          AND date < ?
        """,
        (user_id, pstart, pend),
    ).fetchall()

    prev_exp = 0.0
    for r in prev_rows:
        t = (r[0] or "").upper().strip()
        a = float(r[1] or 0.0)
        if "INGRESO" not in t:
            prev_exp += a

    conn.close()

    balance = income - expense
    by_cat_sorted = dict(sorted(by_cat.items(), key=lambda kv: kv[1], reverse=True))
    return {
        "month": month_yyyy_mm,
        "user": user_name,
        "income": income,
        "expense": expense,
        "balance": balance,
        "by_cat": by_cat_sorted,
        "prev_exp": prev_exp,
    }


def compute_stats_all(month_yyyy_mm: str) -> dict[str, Any]:
    """
    Estadísticas del mes agregando TODOS los usuarios (agregado global).
    No filtra por user_id. Para stats por usuario, usar compute_stats.
    prev_exp se deja en 0 (el resumen CLI no lo muestra).
    """
    y, m = map(int, month_yyyy_mm.split("-"))
    start = date(y, m, 1)
    end = date(y + 1, 1, 1) if m == 12 else date(y, m + 1, 1)
    start_s, end_s = start.isoformat(), end.isoformat()

    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT type, category, SUM(amount)
        FROM transactions
        WHERE date >= ? AND date < ?
        GROUP BY type, category
        """,
        (start_s, end_s),
    )
    rows = cur.fetchall()
    conn.close()

    income = 0.0
    expense = 0.0
    by_cat = {}
    for t, cat, amt in rows:
        amt = amt or 0
        if (t or "").strip().upper() == "INGRESO":
            income += amt
        else:
            expense += amt
            by_cat[cat or "SIN CATEGORIA"] = by_cat.get(cat or "SIN CATEGORIA", 0.0) + amt
    balance = income - expense
    by_cat_sorted = dict(sorted(by_cat.items(), key=lambda kv: kv[1], reverse=True))
    return {
        "month": month_yyyy_mm,
        "user": "ALL",
        "income": income,
        "expense": expense,
        "balance": balance,
        "by_cat": by_cat_sorted,
        "prev_exp": 0.0,
    }


def format_stats(st: dict[str, Any]) -> str:
    """Formato para Telegram (Markdown). Incluye porcentajes, promedio diario, ahorro, mayor gasto."""
    m = st["month"]
    u = st["user"].upper()
    inc = st["income"]
    exp = st["expense"]
    bal = st["balance"]
    prev = st["prev_exp"]
    by_cat = st["by_cat"]

    diff = exp - prev
    pct = (diff / prev * 100.0) if prev > 0 else 0.0

    if prev > 0:
        variacion_line = f"Variación: `${diff:,.2f} CAD` ({pct:.1f}%)"
    else:
        variacion_line = "Variación: N/A (sin datos previos)"

    # Promedio diario
    days = _days_for_daily_avg(m)
    daily_avg = (exp / days) if days > 0 else 0.0
    daily_line = f"Promedio diario gasto: `${daily_avg:,.2f} CAD`"

    # Tasa de ahorro
    ahorro_line = f"Ahorro: {(bal / inc * 100):.1f}%" if inc > 0 else "Ahorro: N/A"

    # Mayor gasto
    top_cat = next(iter(by_cat), None)
    mayor_line = f"Mayor gasto: {top_cat}" if top_cat else "Mayor gasto: N/A"

    lines = [
        f"📊 *Stats {u} | {m}*",
        "",
        f"Ingresos: `${inc:,.2f} CAD`",
        f"Gastos:   `${exp:,.2f} CAD`",
        f"Balance:  `${bal:,.2f} CAD`",
        "",
        f"Mes anterior (gastos): `${prev:,.2f} CAD`",
        variacion_line,
        "",
        daily_line,
        ahorro_line,
        mayor_line,
        "",
        "*Top categorías (egresos):*",
    ]
    top = list(by_cat.items())[:7]
    total_exp = exp
    if not top:
        lines.append("- sin gastos")
    else:
        for cat, val in top:
            pct_cat = (val / total_exp * 100.0) if total_exp > 0 else 0.0
            lines.append(f"- {cat}: `${val:,.2f} CAD` ({pct_cat:.1f}%)")
    return "\n".join(lines)


# --- Analytics helpers below are not wired to telegram_bot or CLI today; kept for future use. ---


def compute_category_breakdown(user_name: str, month_yyyy_mm: str) -> list[dict[str, Any]]:
    """
    Gasto total por categoría con porcentaje sobre el total de egresos.
    Reutiliza compute_stats; no hace queries adicionales.
    (Not used by bot/CLI in this repo; see module note above.)
    """
    st = compute_stats(user_name, month_yyyy_mm)
    by_cat = st["by_cat"]
    total = sum(by_cat.values()) if by_cat else 0.0
    result = []
    for cat, amount in by_cat.items():
        pct = (amount / total * 100.0) if total > 0 else 0.0
        result.append({"category": cat, "amount": amount, "pct": round(pct, 1)})
    return result


def compute_payment_method_breakdown(user_name: str, month_yyyy_mm: str) -> list[dict[str, Any]]:
    """
    Gasto por método de pago (solo egresos).
    Incluye porcentaje sobre el total de egresos del mes.
    (Not used by bot/CLI in this repo; see module note above.)
    """
    start, end = month_range(month_yyyy_mm)
    conn = get_conn()
    cur = conn.cursor()
    row = cur.execute("SELECT id FROM users WHERE lower(name)=lower(?)", (user_name,)).fetchone()
    if not row:
        conn.close()
        return []

    user_id = row[0]
    cur.execute(
        """
        SELECT payment_method, SUM(amount)
        FROM transactions
        WHERE user_id = ?
          AND date >= ? AND date < ?
          AND UPPER(TRIM(COALESCE(type, ''))) != 'INGRESO'
        GROUP BY payment_method
        ORDER BY 2 DESC
        """,
        (user_id, start, end),
    )
    rows = cur.fetchall()
    conn.close()

    total = sum(r[1] or 0 for r in rows)
    result = []
    for pm, amount in rows:
        amt = float(amount or 0)
        pct = (amt / total * 100.0) if total > 0 else 0.0
        result.append({
            "payment_method": pm or "SIN MÉTODO",
            "amount": amt,
            "pct": round(pct, 1),
        })
    return result


def compute_top_merchants(
    user_name: str, month_yyyy_mm: str, limit: int = 5
) -> list[dict[str, Any]]:
    """
    Comercios más frecuentes basados en description (solo egresos).
    Extrae la parte antes del primer número como merchant.
    Ordenado por cantidad de transacciones (más frecuente primero).
    (Not used by bot/CLI in this repo; see module note above.)
    """
    start, end = month_range(month_yyyy_mm)
    conn = get_conn()
    cur = conn.cursor()
    row = cur.execute("SELECT id FROM users WHERE lower(name)=lower(?)", (user_name,)).fetchone()
    if not row:
        conn.close()
        return []

    user_id = row[0]
    cur.execute(
        """
        SELECT description, COUNT(*) as cnt, SUM(amount) as total
        FROM transactions
        WHERE user_id = ?
          AND date >= ? AND date < ?
          AND UPPER(TRIM(COALESCE(type, ''))) != 'INGRESO'
        GROUP BY description
        """,
        (user_id, start, end),
    )
    rows = cur.fetchall()
    conn.close()

    # Agrupar por merchant (parte antes del primer número)
    merchant_agg: dict[str, tuple[int, float]] = {}
    for desc, cnt, amt in rows:
        m = re.match(r"^([^\d]+)", (desc or "").strip())
        merchant = (m.group(1).strip() if m else (desc or "").strip()) or "Otros"
        # Quitar prefijos comunes "gasto " / "ingreso "
        for prefix in ("gasto ", "ingreso "):
            if merchant.lower().startswith(prefix):
                merchant = merchant[len(prefix) :].strip()
                break
        merchant = merchant.title() or "Otros"
        if merchant not in merchant_agg:
            merchant_agg[merchant] = (0, 0.0)
        merchant_agg[merchant] = (
            merchant_agg[merchant][0] + cnt,
            merchant_agg[merchant][1] + float(amt or 0),
        )

    sorted_merchants = sorted(
        merchant_agg.items(), key=lambda x: x[1][0], reverse=True
    )[:limit]
    return [
        {"merchant": m, "count": c, "total": round(t, 2)}
        for m, (c, t) in sorted_merchants
    ]


def compute_month_comparison(user_name: str, month_yyyy_mm: str) -> dict[str, Any]:
    """
    Compara ingresos y gastos del mes actual vs mes anterior.
    Devuelve porcentaje de cambio. Reutiliza compute_stats.
    (Not used by bot/CLI in this repo; see module note above.)
    """
    st_curr = compute_stats(user_name, month_yyyy_mm)
    prev_m = prev_month(month_yyyy_mm)
    st_prev = compute_stats(user_name, prev_m)

    curr_income = st_curr["income"]
    curr_expense = st_curr["expense"]
    prev_income = st_prev["income"]
    prev_expense = st_prev["expense"]

    income_pct = (curr_income - prev_income) / prev_income * 100.0 if prev_income > 0 else None
    expense_pct = (curr_expense - prev_expense) / prev_expense * 100.0 if prev_expense > 0 else None

    return {
        "month": month_yyyy_mm,
        "prev_month": prev_m,
        "curr_income": curr_income,
        "curr_expense": curr_expense,
        "prev_income": prev_income,
        "prev_expense": prev_expense,
        "income_pct_change": round(income_pct, 1) if income_pct is not None else None,
        "expense_pct_change": round(expense_pct, 1) if expense_pct is not None else None,
    }


def compute_summary_data(
    user_name: str, month_yyyy_mm: str, today_yyyy_mm_dd: str
) -> dict[str, Any]:
    """
    Datos para el resumen: hoy, mes, top 3 categorías, presupuestos en alerta (>= 80%).
    today_yyyy_mm_dd: fecha de hoy en formato YYYY-MM-DD (resuelta por el caller).
    """
    st = compute_stats(user_name, month_yyyy_mm)
    start, end = month_range(month_yyyy_mm)

    conn = get_conn()
    try:
        row = conn.execute("SELECT id FROM users WHERE lower(name)=lower(?)", (user_name,)).fetchone()
        if not row:
            return {
                "user": user_name,
                "month": month_yyyy_mm,
                "today_income": 0.0,
                "today_expense": 0.0,
                "month_income": st["income"],
                "month_expense": st["expense"],
                "month_balance": st["balance"],
                "top_categories": [],
                "budget_alerts": [],
                "prev_month_expense": st["prev_exp"],
            }

        user_id = row[0]
        today_income, today_expense = get_income_expense_for_date(conn, user_id, today_yyyy_mm_dd)

        rows = get_budgets(conn, user_id)
        expenses = get_expense_by_category_for_month(conn, user_id, start, end)

        budget_alerts = []
        for cat, budget_amt, _ in rows:
            budget_amt = float(budget_amt)
            if budget_amt <= 0:
                continue
            spent = expenses.get(cat, 0.0)
            pct = (spent / budget_amt * 100.0)
            if pct >= 80:
                budget_alerts.append({"category": cat, "pct": round(pct)})
    finally:
        conn.close()

    top_categories = list(st["by_cat"].items())[:3]
    top_cat = top_categories[0][0] if top_categories else None

    return {
        "user": user_name,
        "month": month_yyyy_mm,
        "today_income": today_income,
        "today_expense": today_expense,
        "month_income": st["income"],
        "month_expense": st["expense"],
        "month_balance": st["balance"],
        "top_categories": top_categories,
        "budget_alerts": budget_alerts,
        "_mayor_gasto": top_cat,
        "prev_month_expense": st["prev_exp"],
    }


def compute_summary_data_all(month_yyyy_mm: str, today_yyyy_mm_dd: str) -> dict[str, Any]:
    """
    Datos para el resumen ALL: hoy (agregado), mes (compute_stats_all).
    Reutiliza compute_stats_all y get_income_expense_for_date.
    """
    st = compute_stats_all(month_yyyy_mm)
    st_prev = compute_stats_all(prev_month(month_yyyy_mm))
    prev_month_expense_all = st_prev["expense"]
    today_income, today_expense = 0.0, 0.0
    conn = get_conn()
    try:
        for user_id, _ in get_all_users(conn):
            inc, exp = get_income_expense_for_date(conn, user_id, today_yyyy_mm_dd)
            today_income += inc
            today_expense += exp
    finally:
        conn.close()

    top_cat = next(iter(st["by_cat"]), None)
    return {
        "user": "ALL",
        "month": month_yyyy_mm,
        "today_income": today_income,
        "today_expense": today_expense,
        "month_income": st["income"],
        "month_expense": st["expense"],
        "month_balance": st["balance"],
        "top_categories": list(st["by_cat"].items())[:3],
        "budget_alerts": [],
        "_mayor_gasto": top_cat,
        "_expense": st["expense"],
        "prev_month_expense": prev_month_expense_all,
    }


def format_summary(data: dict[str, Any]) -> str:
    """
    Resumen compacto: hoy, mes, vs mes anterior, proyección fin de mes, insights, mayor gasto.
    """
    u = data["user"]
    m = data["month"]
    exp = data.get("_expense", data["month_expense"])
    bal = data["month_balance"]
    prev_e = float(data.get("prev_month_expense") or 0.0)
    mayor = data.get("_mayor_gasto") or (
        data["top_categories"][0][0] if data.get("top_categories") else None
    )

    days_elapsed = _days_for_daily_avg(m)
    y, mon = map(int, m.split("-"))
    days_total = calendar.monthrange(y, mon)[1]
    daily_avg = (exp / days_elapsed) if days_elapsed > 0 else 0.0
    projected = daily_avg * days_total

    lines = [
        f"📌 Summary {u} | {m}",
        "",
        f"Hoy — Ing. ${data['today_income']:,.2f} · Gast. ${data['today_expense']:,.2f} CAD",
        f"Mes — Ing. ${data['month_income']:,.2f} · Gast. ${exp:,.2f} · Bal. ${bal:,.2f} CAD",
        "",
    ]

    if prev_e > 0:
        pct_vs = (exp - prev_e) / prev_e * 100.0
        sign = "+" if pct_vs >= 0 else ""
        lines.append(f"Vs mes ant. (gasto): {sign}{pct_vs:.1f}%")
    else:
        lines.append("Vs mes ant. (gasto): N/A")

    lines.append(f"Proy. fin de mes: ~${projected:,.2f} CAD")
    lines.append("")

    insights: list[str] = []
    if prev_e > 0 and exp > prev_e:
        insights.append("⚠️ Gasto por encima del mes anterior")
    if bal > 0:
        insights.append("✓ Balance positivo")
    if insights:
        lines.extend(insights)
        lines.append("")

    lines.append(f"Mayor gasto: {mayor}" if mayor else "Mayor gasto: N/A")
    return "\n".join(lines)


def format_weekly_report(data: dict[str, Any]) -> str:
    """
    Formato ejecutivo para el reporte semanal.
    Incluye: ingresos, gastos, balance, top 3, alertas (80-99%), excedidas (≥100%).
    Omite secciones vacías.
    """
    u = data["user"]
    m = data["month"]
    lines = [
        f"📬 Reporte semanal | {u} | {m}",
        "",
        f"Ingresos: ${data['month_income']:,.2f} CAD",
        f"Gastos:   ${data['month_expense']:,.2f} CAD",
        f"Balance:  ${data['month_balance']:,.2f} CAD",
    ]

    if data["top_categories"]:
        lines.append("")
        lines.append("Top 3 categorías:")
        for cat, amt in data["top_categories"]:
            lines.append(f"• {cat}: ${amt:,.2f} CAD")

    alertas = [a for a in data["budget_alerts"] if 80 <= a["pct"] < 100]
    excedidas = [a for a in data["budget_alerts"] if a["pct"] >= 100]

    if alertas:
        lines.append("")
        lines.append("⚠️ Presupuestos en alerta (≥80%):")
        for a in alertas:
            lines.append(f"• {a['category']}: {a['pct']}%")

    if excedidas:
        lines.append("")
        lines.append("🚨 Excedidos:")
        for a in excedidas:
            lines.append(f"• {a['category']}: {a['pct']}%")

    return "\n".join(lines)


def format_resumen(st: dict[str, Any]) -> str:
    """Formato para CLI (resumen_mes). Sin prev_exp ni variación."""
    m = st["month"]
    inc = st["income"]
    exp = st["expense"]
    bal = st["balance"]
    by_cat = st["by_cat"]

    lines = [
        f"\n📊 Resumen {m}",
        f"Ingresos: ${inc:.2f}",
        f"Egresos: ${exp:.2f}",
        f"Balance: ${bal:.2f}\n",
        "Gastos por categoría:",
    ]
    for c, v in by_cat.items():
        lines.append(f"- {c}: ${v:.2f}")
    return "\n".join(lines)
