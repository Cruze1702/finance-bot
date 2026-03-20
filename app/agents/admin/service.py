"""
High-level use cases for the finance bot.
Orchestrates parser, repositories, stats, and excel.
"""
from datetime import datetime

from app.agents.admin import excel
from app.agents.admin.models import BUDGET_BLOCKED_CATEGORIES, DEFAULT_CURRENCY, USERS
from app.agents.admin.parser import (
    detect_category,
    detect_income_category,
    detect_payment,
    extract_amount,
    is_ingreso,
    normalize_category,
    resolve_income_category_for_input,
)
from app.agents.admin.repositories import (
    get_conn,
    ensure_user,
    get_user_id,
    get_last_transaction,
    get_last_transactions,
    delete_transaction_by_id,
    update_transaction_amount,
    insert_transaction,
    upsert_budget,
    get_budget,
    get_budgets,
    delete_budget,
    get_budget_alert_level,
    upsert_budget_alert_level,
    delete_transactions_for_month,
    delete_budget_alert_state_for_month,
    get_expense_by_category_for_month,
)
from app.agents.admin import stats


def add_transaction(user_display_name: str, text: str) -> dict:
    """
    Registra una transacción a partir del texto libre.
    user_display_name: nombre tal como está en la DB (ej. "Cross", "Pau").
    Si el texto contiene coma, la parte antes se usa para categoría/pago/monto
    y la parte después como descripción guardada.
    Imprime confirmación o error a stdout (comportamiento CLI actual) y
    devuelve un diccionario estructurado con el resultado.
    """
    text_original = text
    if "," in text:
        main_text, description = text.split(",", 1)
        main_text = main_text.strip()
        description = description.strip()
    else:
        main_text = text
        description = text

    result: dict = {
        "success": False,
        "type": None,
        "amount": None,
        "category": None,
        "payment_method": None,
        "description": description,
        "message": "",
    }

    ensure_user(user_display_name)
    conn = get_conn()
    try:
        user_id = get_user_id(conn, user_display_name)
        if user_id is None:
            msg = "❌ Usuario no encontrado"
            print(msg)
            result["message"] = msg
            return result

        amount = extract_amount(main_text)
        if amount is None:
            msg = "❌ No encontré monto"
            print(msg)
            result["message"] = msg
            return result

        tx_type = "INGRESO" if is_ingreso(main_text) else "EGRESO"
        category = detect_income_category(main_text) if tx_type == "INGRESO" else detect_category(main_text)
        payment = detect_payment(main_text)
        now = datetime.now()
        ts = now.strftime("%Y-%m-%d %H:%M:%S")
        date_str = now.strftime("%Y-%m-%d")

        insert_transaction(
            conn, user_id, ts, date_str, description, category, payment, tx_type, amount, DEFAULT_CURRENCY,
            raw_text=text_original,
        )
        conn.commit()

        sign = "-" if tx_type == "EGRESO" else "+"
        msg = (
            f"✅ {user_display_name} | {tx_type} | "
            f"{sign}${amount:.2f} {DEFAULT_CURRENCY} | {category} | {payment}"
        )
        print(msg)

        result.update(
            {
                "success": True,
                "type": tx_type,
                "amount": float(amount),
                "category": category,
                "payment_method": payment,
                "message": msg,
            }
        )
        return result
    finally:
        conn.close()


def get_weekly_report(
    user_display_name: str, month: str | None = None, today_str: str | None = None
) -> dict:
    """
    Reporte semanal ejecutivo: ingresos, gastos, balance, top 3, alertas, excedidas.
    Reutiliza compute_summary_data y format_weekly_report.
    """
    month = month or datetime.now().strftime("%Y-%m")
    today_str = today_str or datetime.now().strftime("%Y-%m-%d")

    try:
        data = stats.compute_summary_data(user_display_name, month, today_str)
        msg = stats.format_weekly_report(data)
        return {"success": True, "message": msg}
    except Exception as e:
        return {"success": False, "message": f"❌ No pude generar reporte:\n{e}"}


def get_summary(
    user_display_name: str,
    month: str | None = None,
    today_str: str | None = None,
) -> dict:
    """
    Resumen financiero: hoy, mes, top 3 categorías, presupuestos en alerta.
    month y today_str se resuelven por el caller (ej. bot con TZ).
    Si no se pasan, usa datetime.now().
    """
    month = month or datetime.now().strftime("%Y-%m")
    today_str = today_str or datetime.now().strftime("%Y-%m-%d")

    try:
        data = stats.compute_summary_data(user_display_name, month, today_str)
        msg = stats.format_summary(data)
        return {"success": True, "message": msg}
    except Exception as e:
        return {"success": False, "message": f"❌ No pude generar resumen:\n{e}"}


def resumen_mes(user: str | None = None) -> None:
    """
    Imprime resumen del mes actual.
    user: "Cross", "Pau" o None para agregado de todos los usuarios.
    """
    month = datetime.now().strftime("%Y-%m")
    if user is None:
        st = stats.compute_stats_all(month)
    else:
        st = stats.compute_stats(user, month)
    print(stats.format_resumen(st))


def export_excel_template(month: str | None = None):
    """
    Genera Excel del mes actual usando plantilla (comando excel).
    Devuelve Path del archivo generado o None si falla (ej. plantilla no existe).
    """
    return excel.export_excel_template_copy(month)


def export_movimientos() -> None:
    """Genera Excel limpio del mes actual (comando movimientos)."""
    excel.export_movimientos_excel()


def list_last_transactions(
    user_display_name: str, limit: int = 5
) -> dict:
    """
    Últimas N transacciones del usuario.
    Devuelve {success, message, transactions}.
    """
    conn = get_conn()
    try:
        user_id = get_user_id(conn, user_display_name)
        if user_id is None:
            return {"success": False, "message": "❌ Usuario no encontrado", "transactions": []}

        rows = get_last_transactions(conn, user_id, limit)
        if not rows:
            return {"success": True, "message": "❌ No hay transacciones.", "transactions": []}

        lines = [f"📋 Últimas {len(rows)} transacciones ({user_display_name}):"]
        for i, r in enumerate(rows, 1):
            tx_id, date_s, desc, cat, pm, tx_type, amt, curr = (
                r[0], r[1], r[2] or "", r[3] or "SIN CATEGORIA", r[4], r[5] or "EGRESO", float(r[6] or 0), r[7] or "CAD"
            )
            sign = "-" if (tx_type or "").upper().strip() != "INGRESO" else "+"
            lines.append(f"{i}. {date_s} | {tx_type} | {desc} | {sign}${amt:,.2f} {curr} | {cat}")
        return {"success": True, "message": "\n".join(lines), "transactions": rows}
    finally:
        conn.close()


def delete_last_transaction(user_display_name: str) -> dict:
    """
    Borra la última transacción del usuario.
    Devuelve {success, message}.
    """
    conn = get_conn()
    try:
        user_id = get_user_id(conn, user_display_name)
        if user_id is None:
            return {"success": False, "message": "❌ Usuario no encontrado"}

        row = get_last_transaction(conn, user_id)
        if row is None:
            return {"success": False, "message": "❌ No había transacciones."}

        tx_id, date_s, desc, cat, pm, tx_type, amt, curr = (
            row[0], row[1], row[2] or "", row[3], row[4], row[5] or "", float(row[6] or 0), row[7] or "CAD"
        )
        sign = "-" if (tx_type or "").upper().strip() != "INGRESO" else "+"
        delete_transaction_by_id(conn, tx_id)
        conn.commit()
        msg = f"✅ Transacción eliminada: {desc} ({sign}${amt:,.2f})"
        return {"success": True, "message": msg}
    finally:
        conn.close()


def edit_last_transaction_amount(
    user_display_name: str, new_amount: float
) -> dict:
    """
    Actualiza el monto de la última transacción del usuario.
    Devuelve {success, message}.
    """
    if new_amount <= 0:
        return {"success": False, "message": "❌ El monto debe ser mayor a 0."}

    conn = get_conn()
    try:
        user_id = get_user_id(conn, user_display_name)
        if user_id is None:
            return {"success": False, "message": "❌ Usuario no encontrado"}

        row = get_last_transaction(conn, user_id)
        if row is None:
            return {"success": False, "message": "❌ No había transacciones."}

        tx_id, old_amt = row[0], float(row[6] or 0)
        update_transaction_amount(conn, tx_id, new_amount)
        conn.commit()
        msg = f"✅ Monto actualizado: ${new_amount:,.2f} (antes ${old_amt:,.2f})"
        return {"success": True, "message": msg}
    finally:
        conn.close()


def set_budget(
    user_display_name: str, category_input: str, amount: float, currency: str = "CAD"
) -> dict:
    """
    Crea o actualiza el presupuesto de una categoría.
    category_input se normaliza con normalize_category. Error si no se reconoce.
    """
    if amount <= 0:
        return {"success": False, "message": "❌ El monto debe ser mayor a 0."}

    income_cat = resolve_income_category_for_input(category_input)
    if income_cat is not None:
        return {
            "success": False,
            "message": "❌ No puedes definir presupuestos para categorías de ingreso. Los presupuestos solo aplican a gastos.",
        }

    category = normalize_category(category_input)
    if category is None:
        return {
            "success": False,
            "message": f"❌ Categoría no reconocida: '{category_input}'. Ej: comida, transporte, hogar.",
        }
    if category in BUDGET_BLOCKED_CATEGORIES:
        return {
            "success": False,
            "message": "❌ No puedes definir presupuestos para categorías de ingreso. Los presupuestos solo aplican a gastos.",
        }

    conn = get_conn()
    try:
        user_id = get_user_id(conn, user_display_name)
        if user_id is None:
            return {"success": False, "message": "❌ Usuario no encontrado"}

        upsert_budget(conn, user_id, category, amount, currency)
        conn.commit()
        return {"success": True, "message": f"✅ Presupuesto {category}: ${amount:,.2f} {currency}"}
    finally:
        conn.close()


def get_budget_status(
    user_display_name: str, category_input: str, month: str | None = None
) -> dict:
    """
    Estado del presupuesto de una categoría: presupuesto, gastado, disponible, porcentaje.
    """
    category = normalize_category(category_input)
    if category is None:
        return {
            "success": False,
            "message": f"❌ Categoría no reconocida: '{category_input}'. Ej: comida, transporte, hogar.",
        }

    month = month or datetime.now().strftime("%Y-%m")
    start, end = stats.month_range(month)

    conn = get_conn()
    try:
        user_id = get_user_id(conn, user_display_name)
        if user_id is None:
            return {"success": False, "message": "❌ Usuario no encontrado"}

        row = get_budget(conn, user_id, category)
        expenses = get_expense_by_category_for_month(conn, user_id, start, end)
        spent = expenses.get(category, 0.0)
    finally:
        conn.close()

    budget_amt = float(row[1]) if row else None
    curr = row[2] if row else "CAD"

    lines = [f"📋 {category} | {month}", ""]
    if budget_amt is None:
        lines.append("Presupuesto: — (no definido)")
        lines.append(f"Gastado:     ${spent:,.2f} {curr}")
    else:
        available = budget_amt - spent
        pct = (spent / budget_amt * 100.0) if budget_amt > 0 else 0.0
        lines.append(f"Presupuesto: ${budget_amt:,.2f} {curr}")
        lines.append(f"Gastado:     ${spent:,.2f} {curr} ({pct:.0f}%)")
        lines.append(f"Disponible:  ${available:,.2f} {curr}")
    return {"success": True, "message": "\n".join(lines)}


def list_budgets_status(
    user_display_name: str, month: str | None = None
) -> dict:
    """
    Lista presupuestos con gastado, disponible y porcentaje.
    Solo categorías con presupuesto definido. Si no hay, error claro.
    """
    month = month or datetime.now().strftime("%Y-%m")
    start, end = stats.month_range(month)

    conn = get_conn()
    try:
        user_id = get_user_id(conn, user_display_name)
        if user_id is None:
            return {"success": False, "message": "❌ Usuario no encontrado"}

        rows = get_budgets(conn, user_id)
        if not rows:
            return {"success": False, "message": "❌ No tienes presupuestos definidos."}

        expenses = get_expense_by_category_for_month(conn, user_id, start, end)
    finally:
        conn.close()

    lines = [f"📋 Presupuestos ({user_display_name}) | {month}", ""]
    for cat, budget_amt, curr in rows:
        budget_amt = float(budget_amt)
        spent = expenses.get(cat, 0.0)
        available = budget_amt - spent
        pct = (spent / budget_amt * 100.0) if budget_amt > 0 else 0
        lines.append(
            f"{cat}: ${budget_amt:,.2f} | ${spent:,.2f} gastado ({pct:.0f}%) | ${available:,.2f} disponible"
        )
    return {"success": True, "message": "\n".join(lines)}


def check_budget_alert(
    user_display_name: str, category: str, month: str | None = None
) -> dict | None:
    """
    Revisa si la categoría tiene presupuesto y si el gasto acumulado alcanza
    umbrales de alerta (80% o 100%).
    Solo devuelve alerta si el nivel actual supera el último nivel ya alertado
    (evita repeticiones en el mismo mes).
    Devuelve None si no hay presupuesto, budget_amt <= 0, no alcanza 80%, o ya se alertó.
    Devuelve {"message": "..."} con el texto de alerta en caso contrario.
    """
    month = month or datetime.now().strftime("%Y-%m")
    start, end = stats.month_range(month)

    conn = get_conn()
    try:
        user_id = get_user_id(conn, user_display_name)
        if user_id is None:
            return None

        row = get_budget(conn, user_id, category)
        if row is None:
            return None

        budget_amt = float(row[1])
        curr = row[2] or "CAD"

        if budget_amt <= 0:
            return None

        expenses = get_expense_by_category_for_month(conn, user_id, start, end)
        spent = expenses.get(category, 0.0)
        pct = (spent / budget_amt * 100.0) if budget_amt > 0 else 0.0

        if pct >= 100:
            current_level = 2
        elif pct >= 80:
            current_level = 1
        else:
            return None

        stored_level = get_budget_alert_level(conn, user_id, category, month)
        if current_level <= stored_level:
            return None

        if current_level == 2:
            excess = spent - budget_amt
            alert_msg = (
                f"🚨 Presupuesto {category} excedido\n"
                f"Gastado: ${spent:,.2f} de ${budget_amt:,.2f} {curr}\n"
                f"Exceso: ${excess:,.2f} {curr}"
            )
        else:
            available = budget_amt - spent
            alert_msg = (
                f"⚠️ Presupuesto {category}: {pct:.0f}% usado\n"
                f"Gastado: ${spent:,.2f} de ${budget_amt:,.2f} {curr}\n"
                f"Disponible: ${available:,.2f} {curr}"
            )

        upsert_budget_alert_level(conn, user_id, category, month, current_level)
        conn.commit()
        return {"message": alert_msg}
    finally:
        conn.close()


def reset_month_data(user_display_name: str) -> dict:
    """
    Borra transacciones y estado de alertas del mes actual para el usuario.
    No toca presupuestos ni usuarios.
    """
    month = datetime.now().strftime("%Y-%m")
    start, end = stats.month_range(month)

    conn = get_conn()
    try:
        user_id = get_user_id(conn, user_display_name)
        if user_id is None:
            return {"success": False, "message": "❌ Usuario no encontrado"}

        tx_deleted = delete_transactions_for_month(conn, user_id, start, end)
        alerts_deleted = delete_budget_alert_state_for_month(conn, user_id, month)
        conn.commit()

        msg = (
            f"🧹 Datos del mes actual reiniciados\n\n"
            f"Mes: {month}\n"
            f"Transacciones eliminadas: {tx_deleted}\n"
            f"Alertas reiniciadas: {alerts_deleted}"
        )
        return {"success": True, "message": msg}
    finally:
        conn.close()


def delete_budget_for_category(
    user_display_name: str, category_input: str
) -> dict:
    """Elimina el presupuesto de una categoría."""
    category = normalize_category(category_input)
    if category is None:
        return {
            "success": False,
            "message": f"❌ Categoría no reconocida: '{category_input}'. Ej: comida, transporte, hogar.",
        }

    conn = get_conn()
    try:
        user_id = get_user_id(conn, user_display_name)
        if user_id is None:
            return {"success": False, "message": "❌ Usuario no encontrado"}

        row = get_budget(conn, user_id, category)
        if row is None:
            return {"success": False, "message": f"❌ No tenías presupuesto para {category}."}

        delete_budget(conn, user_id, category)
        conn.commit()
        return {"success": True, "message": f"✅ Presupuesto {category} eliminado."}
    finally:
        conn.close()
