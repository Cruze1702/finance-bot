"""
High-level use cases for the finance bot.
Orchestrates parser, repositories, stats, and excel.
"""
from datetime import datetime

from app.agents.admin import excel
from app.agents.admin.models import (
    BUDGET_BLOCKED_CATEGORIES,
    DEFAULT_CURRENCY,
    SHARED_BUDGET_OWNER_DISPLAY_NAME,
    TZ,
    USERS,
    category_db_variants,
)
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
    update_transaction_category,
    insert_transaction,
    upsert_budget,
    get_budget,
    get_budgets,
    delete_budget,
    get_budget_alert_level,
    upsert_budget_alert_level,
    delete_transactions_for_month,
    delete_budget_alert_state_for_month,
    get_household_expense_by_category_for_month,
    get_egreso_transactions_all_category_month,
    get_egreso_transactions_user_category_month,
)
from app.agents.admin import stats

# Misma ventana que `last` / delete <n> / edit <n> (índice 1 = más reciente).
RECENT_TRANSACTIONS_LIMIT = 5


def _household_budget_owner_id(conn) -> int | None:
    """user_id bajo el cual viven las filas de budgets compartidos (ver models)."""
    return get_user_id(conn, SHARED_BUDGET_OWNER_DISPLAY_NAME)


def get_category_movements_report(
    user_display_name: str,
    category_input: str,
    month: str | None = None,
) -> dict:
    """
    Movimientos EGRESO del mes por categoría canónica: bloque usuario + bloque ALL (hogar).
    """
    category = normalize_category(category_input)
    if category is None:
        return {
            "success": False,
            "message": (
                f"❌ Categoría no reconocida: '{category_input.strip() or '(vacío)'}'. "
                "Ej: comida, transporte, suscripciones, subscripciones."
            ),
        }

    month = month or datetime.now(TZ).strftime("%Y-%m")
    start, end = stats.month_range(month)
    variants = category_db_variants(category)

    conn = get_conn()
    try:
        user_id = get_user_id(conn, user_display_name)
        if user_id is None:
            return {"success": False, "message": "❌ Usuario no encontrado"}

        rows_me = get_egreso_transactions_user_category_month(
            conn, user_id, variants, start, end
        )
        rows_all = get_egreso_transactions_all_category_month(conn, variants, start, end)
    finally:
        conn.close()

    def _fmt_money(x: float) -> str:
        return f"${x:,.2f}"

    lines = [f"🧾 Categoría {category} | {month}", "", "TU RESUMEN", ""]
    total_me = 0.0
    if not rows_me:
        lines.append("(sin movimientos de egreso en esta categoría este mes.)")
    else:
        for i, r in enumerate(rows_me, 1):
            date_s, desc, amt = r[0], (r[1] or "").strip(), float(r[2] or 0)
            total_me += amt
            lines.append(f"{i}. {date_s} — {desc} — {_fmt_money(amt)}")
        lines.append(f"Total: {_fmt_money(total_me)}")

    lines.extend(["", "ALL", ""])
    total_all = 0.0
    if not rows_all:
        lines.append("(sin movimientos de egreso en esta categoría este mes.)")
    else:
        for i, r in enumerate(rows_all, 1):
            date_s, desc, amt, uname = r[0], (r[1] or "").strip(), float(r[2] or 0), r[3]
            total_all += amt
            lines.append(f"{i}. {date_s} — {desc} — {uname} — {_fmt_money(amt)}")
        lines.append(f"Total: {_fmt_money(total_all)}")

    return {"success": True, "message": "\n".join(lines)}


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
        now = datetime.now(TZ)
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
    month = month or datetime.now(TZ).strftime("%Y-%m")
    today_str = today_str or datetime.now(TZ).strftime("%Y-%m-%d")

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
    Resumen financiero compacto: bloque personal + bloque ALL.
    Hoy, mes, promedio diario, mayor gasto. month y today_str por caller.
    """
    month = month or datetime.now(TZ).strftime("%Y-%m")
    today_str = today_str or datetime.now(TZ).strftime("%Y-%m-%d")

    try:
        data_personal = stats.compute_summary_data(user_display_name, month, today_str)
        data_all = stats.compute_summary_data_all(month, today_str)
        msg = stats.format_summary(data_personal) + "\n\n---\n\n" + stats.format_summary(data_all)
        return {"success": True, "message": msg}
    except Exception as e:
        return {"success": False, "message": f"❌ No pude generar resumen:\n{e}"}


def resumen_mes(user: str | None = None) -> None:
    """
    Imprime resumen del mes actual.
    user: "Cross", "Pau" o None para agregado de todos los usuarios.
    """
    month = datetime.now(TZ).strftime("%Y-%m")
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
    user_display_name: str, limit: int = RECENT_TRANSACTIONS_LIMIT,
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


def delete_recent_transaction_by_index(
    user_display_name: str,
    index: int,
    limit: int = RECENT_TRANSACTIONS_LIMIT,
) -> dict:
    """
    Borra la transacción en la posición index (1 = más reciente) entre las últimas `limit`.
    """
    conn = get_conn()
    try:
        user_id = get_user_id(conn, user_display_name)
        if user_id is None:
            return {"success": False, "message": "❌ Usuario no encontrado"}

        rows = get_last_transactions(conn, user_id, limit)
        if not rows:
            return {"success": False, "message": "❌ No hay transacciones."}

        n = len(rows)
        if index < 1 or index > n:
            return {
                "success": False,
                "message": f"❌ Índice inválido. Usa un número entre 1 y {n} (escribe `last` para ver la lista).",
            }

        row = rows[index - 1]
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


def edit_recent_transaction_amount_by_index(
    user_display_name: str,
    index: int,
    new_amount: float,
    limit: int = RECENT_TRANSACTIONS_LIMIT,
) -> dict:
    """
    Actualiza el monto de la transacción en la posición index (1 = más reciente).
    """
    if new_amount <= 0:
        return {"success": False, "message": "❌ El monto debe ser mayor a 0."}

    conn = get_conn()
    try:
        user_id = get_user_id(conn, user_display_name)
        if user_id is None:
            return {"success": False, "message": "❌ Usuario no encontrado"}

        rows = get_last_transactions(conn, user_id, limit)
        if not rows:
            return {"success": False, "message": "❌ No hay transacciones."}

        n = len(rows)
        if index < 1 or index > n:
            return {
                "success": False,
                "message": f"❌ Índice inválido. Usa un número entre 1 y {n} (escribe `last` para ver la lista).",
            }

        row = rows[index - 1]
        tx_id, old_amt = row[0], float(row[6] or 0)
        update_transaction_amount(conn, tx_id, new_amount)
        conn.commit()
        msg = f"✅ Monto actualizado: ${new_amount:,.2f} (antes ${old_amt:,.2f})"
        return {"success": True, "message": msg}
    finally:
        conn.close()


def delete_last_transaction(user_display_name: str) -> dict:
    """Borra la última transacción del usuario (equivalente a delete 1)."""
    return delete_recent_transaction_by_index(user_display_name, 1)


def edit_last_transaction_amount(
    user_display_name: str, new_amount: float
) -> dict:
    """Actualiza el monto de la última transacción (equivalente a edit 1 <monto>)."""
    return edit_recent_transaction_amount_by_index(user_display_name, 1, new_amount)


def edit_category_by_index(
    user_display_name: str,
    index: int,
    category_input: str,
    limit: int = RECENT_TRANSACTIONS_LIMIT,
) -> dict:
    """
    Actualiza la categoría de la transacción en la posición index (1 = más reciente).
    EGRESO: categoría con normalize_category (comando explícito; misma resolución que la validación).
    INGRESO: resolve_income_category_for_input o normalize_category (p. ej. INGRESOS).
    """
    if index < 1:
        return {"success": False, "message": "❌ Índice inválido. Usa last."}

    conn = get_conn()
    try:
        user_id = get_user_id(conn, user_display_name)
        if user_id is None:
            return {"success": False, "message": "❌ Usuario no encontrado"}

        rows = get_last_transactions(conn, user_id, limit)
        if not rows:
            return {"success": False, "message": "❌ No hay transacciones."}

        n = len(rows)
        if index > n:
            return {"success": False, "message": "❌ Índice inválido. Usa last."}

        row = rows[index - 1]
        tx_id = row[0]
        tx_type = (row[5] or "").upper().strip()

        inc = resolve_income_category_for_input(category_input)
        norm = normalize_category(category_input)

        if tx_type == "INGRESO":
            if inc is not None:
                category = inc
            elif norm is not None:
                category = norm
            else:
                return {"success": False, "message": "❌ Categoría no reconocida."}
        else:
            if norm is None:
                return {"success": False, "message": "❌ Categoría no reconocida."}
            category = norm

        update_transaction_category(conn, tx_id, category)
        conn.commit()
        return {"success": True, "message": f"✅ Categoría actualizada: {category}"}
    finally:
        conn.close()


def set_budget(
    user_display_name: str, category_input: str, amount: float, currency: str = "CAD"
) -> dict:
    """
    Crea o actualiza un budget compartido del hogar (misma fila para Cross y Pau).
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
        caller_id = get_user_id(conn, user_display_name)
        if caller_id is None:
            return {"success": False, "message": "❌ Usuario no encontrado"}

        ensure_user(SHARED_BUDGET_OWNER_DISPLAY_NAME)
        owner_id = get_user_id(conn, SHARED_BUDGET_OWNER_DISPLAY_NAME)
        if owner_id is None:
            return {"success": False, "message": "❌ Usuario no encontrado"}

        upsert_budget(conn, owner_id, category, amount, currency)
        conn.commit()
        return {"success": True, "message": f"✅ Presupuesto {category}: ${amount:,.2f} {currency}"}
    finally:
        conn.close()


def get_budget_status(
    user_display_name: str, category_input: str, month: str | None = None
) -> dict:
    """
    Estado de una categoría: tope en budgets compartidos; gasto del mes = suma hogar (todos los usuarios).
    """
    category = normalize_category(category_input)
    if category is None:
        return {
            "success": False,
            "message": f"❌ Categoría no reconocida: '{category_input}'. Ej: comida, transporte, hogar.",
        }

    month = month or datetime.now(TZ).strftime("%Y-%m")
    # Gasto del mes: solo transacciones EGRESO en [start, end) sobre `date`.
    start, end = stats.month_range(month)

    conn = get_conn()
    try:
        caller_id = get_user_id(conn, user_display_name)
        if caller_id is None:
            return {"success": False, "message": "❌ Usuario no encontrado"}

        owner_id = _household_budget_owner_id(conn)
        row = get_budget(conn, owner_id, category) if owner_id is not None else None
        expenses = get_household_expense_by_category_for_month(conn, start, end)
        spent = expenses.get(category, 0.0)
    finally:
        conn.close()

    budget_amt = float(row[1]) if row else None
    curr = row[2] if row else "CAD"

    lines = [f"📋 {category} | {month}", ""]
    if budget_amt is None:
        lines.append("Tope: — (sin budget configurado)")
        lines.append(f"Gastado (mes): ${spent:,.2f} {curr}")
    else:
        remaining = budget_amt - spent
        pct = (spent / budget_amt * 100.0) if budget_amt > 0 else 0.0
        lines.append(f"Tope: ${budget_amt:,.2f} {curr}")
        lines.append(f"Gastado (mes): ${spent:,.2f} {curr}")
        lines.append(f"Restante: ${remaining:,.2f} {curr}")
        lines.append(f"Usado: {pct:.0f}%")
    return {"success": True, "message": "\n".join(lines)}


def list_budgets_status(
    user_display_name: str, month: str | None = None
) -> dict:
    """
    Lista budgets compartidos del hogar (filas bajo owner canónico; ver models).
    Gastado/restante/% = egresos del mes agregados de todos los usuarios (`date`).
    """
    month = month or datetime.now(TZ).strftime("%Y-%m")
    start, end = stats.month_range(month)

    conn = get_conn()
    try:
        caller_id = get_user_id(conn, user_display_name)
        if caller_id is None:
            return {"success": False, "message": "❌ Usuario no encontrado"}

        owner_id = _household_budget_owner_id(conn)
        if owner_id is None:
            return {"success": False, "message": "No tienes budgets configurados."}

        rows = get_budgets(conn, owner_id)
        if not rows:
            return {"success": False, "message": "No tienes budgets configurados."}

        expenses = get_household_expense_by_category_for_month(conn, start, end)
    finally:
        conn.close()

    lines = [f"📋 Budgets (hogar) | {month}", ""]
    for cat, budget_amt, curr in rows:
        budget_amt = float(budget_amt)
        spent = expenses.get(cat, 0.0)
        remaining = budget_amt - spent
        pct = (spent / budget_amt * 100.0) if budget_amt > 0 else 0.0
        lines.append(f"• {cat}")
        lines.append(f"  Tope: ${budget_amt:,.2f} {curr}")
        lines.append(f"  Gastado: ${spent:,.2f} {curr}")
        lines.append(f"  Restante: ${remaining:,.2f} {curr}")
        lines.append(f"  Usado: {pct:.0f}%")
        lines.append("")
    if lines and lines[-1] == "":
        lines.pop()
    return {"success": True, "message": "\n".join(lines)}


def check_budget_alert(
    user_display_name: str, category: str, month: str | None = None
) -> dict | None:
    """
    Revisa budget compartido del hogar vs gasto agregado del mes; estado de alerta en user_id del owner canónico.
    """
    month = month or datetime.now(TZ).strftime("%Y-%m")
    start, end = stats.month_range(month)

    conn = get_conn()
    try:
        caller_id = get_user_id(conn, user_display_name)
        if caller_id is None:
            return None

        owner_id = _household_budget_owner_id(conn)
        if owner_id is None:
            return None

        row = get_budget(conn, owner_id, category)
        if row is None:
            return None

        budget_amt = float(row[1])
        curr = row[2] or "CAD"

        if budget_amt <= 0:
            return None

        expenses = get_household_expense_by_category_for_month(conn, start, end)
        spent = expenses.get(category, 0.0)
        pct = (spent / budget_amt * 100.0) if budget_amt > 0 else 0.0

        if pct >= 100:
            current_level = 2
        elif pct >= 80:
            current_level = 1
        else:
            return None

        stored_level = get_budget_alert_level(conn, owner_id, category, month)
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

        upsert_budget_alert_level(conn, owner_id, category, month, current_level)
        conn.commit()
        return {"message": alert_msg}
    finally:
        conn.close()


def reset_month_data(user_display_name: str) -> dict:
    """
    Borra transacciones y estado de alertas del mes actual para el usuario.
    No toca presupuestos ni usuarios.
    """
    month = datetime.now(TZ).strftime("%Y-%m")
    start, end = stats.month_range(month)

    conn = get_conn()
    try:
        user_id = get_user_id(conn, user_display_name)
        if user_id is None:
            return {"success": False, "message": "❌ Usuario no encontrado"}

        tx_deleted = delete_transactions_for_month(conn, user_id, start, end)
        alerts_deleted = delete_budget_alert_state_for_month(conn, user_id, month)
        # Alertas de budgets compartidos viven bajo el owner canónico (p. ej. Pau).
        owner_id = _household_budget_owner_id(conn)
        if owner_id is not None and owner_id != user_id:
            alerts_deleted += delete_budget_alert_state_for_month(conn, owner_id, month)
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
    """Elimina el budget compartido de una categoría (fila del owner canónico)."""
    category = normalize_category(category_input)
    if category is None:
        return {
            "success": False,
            "message": f"❌ Categoría no reconocida: '{category_input}'. Ej: comida, transporte, hogar.",
        }

    conn = get_conn()
    try:
        caller_id = get_user_id(conn, user_display_name)
        if caller_id is None:
            return {"success": False, "message": "❌ Usuario no encontrado"}

        owner_id = _household_budget_owner_id(conn)
        if owner_id is None:
            return {"success": False, "message": f"❌ No tenías presupuesto para {category}."}

        row = get_budget(conn, owner_id, category)
        if row is None:
            return {"success": False, "message": f"❌ No tenías presupuesto para {category}."}

        delete_budget(conn, owner_id, category)
        conn.commit()
        return {"success": True, "message": f"✅ Presupuesto {category} eliminado."}
    finally:
        conn.close()
