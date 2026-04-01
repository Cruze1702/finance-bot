"""
SQLite data access: connection, users, transactions, budgets.
"""
import sqlite3
from typing import Optional

from app.agents.admin.models import DB_PATH, STORAGE_DIR


def get_conn() -> sqlite3.Connection:
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users(
            id INTEGER PRIMARY KEY,
            name TEXT UNIQUE
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS transactions(
            id INTEGER PRIMARY KEY,
            user_id INTEGER,
            ts TEXT,
            date TEXT,
            description TEXT,
            category TEXT,
            payment_method TEXT,
            type TEXT,
            amount REAL,
            currency TEXT DEFAULT 'CAD'
        )
    """)
    try:
        conn.execute("ALTER TABLE transactions ADD COLUMN raw_text TEXT")
    except sqlite3.OperationalError:
        pass
    conn.execute("""
        CREATE TABLE IF NOT EXISTS budgets(
            user_id INTEGER NOT NULL,
            category TEXT NOT NULL,
            amount REAL NOT NULL,
            currency TEXT DEFAULT 'CAD',
            PRIMARY KEY (user_id, category),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS budget_alert_state(
            user_id INTEGER NOT NULL,
            category TEXT NOT NULL,
            month TEXT NOT NULL,
            level INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (user_id, category, month),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)
    return conn


def ensure_user(name: str) -> None:
    conn = get_conn()
    conn.execute("INSERT OR IGNORE INTO users(name) VALUES(?)", (name,))
    conn.commit()
    conn.close()


def get_all_users(conn: sqlite3.Connection) -> list:
    """Lista (user_id, name) de todos los usuarios, ordenados por nombre."""
    cur = conn.execute("SELECT id, name FROM users ORDER BY name")
    return cur.fetchall()


def get_user_id(conn: sqlite3.Connection, name: str) -> Optional[int]:
    cur = conn.execute("SELECT id FROM users WHERE name = ?", (name,))
    row = cur.fetchone()
    return row[0] if row else None


def insert_transaction(
    conn: sqlite3.Connection,
    user_id: int,
    ts: str,
    date: str,
    description: str,
    category: str,
    payment_method: str,
    tx_type: str,
    amount: float,
    currency: str,
    raw_text: str | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO transactions(
            user_id, ts, date, description, category,
            payment_method, type, amount, currency, raw_text
        )
        VALUES(?,?,?,?,?,?,?,?,?,?)
        """,
        (user_id, ts, date, description, category, payment_method, tx_type, amount, currency, raw_text),
    )


def get_last_transactions(
    conn: sqlite3.Connection, user_id: int, limit: int = 5
) -> list:
    """Últimas N transacciones del usuario, más reciente primero."""
    cur = conn.execute(
        """
        SELECT id, date, description, category, payment_method, type, amount, currency
        FROM transactions
        WHERE user_id = ?
        ORDER BY id DESC
        LIMIT ?
        """,
        (user_id, limit),
    )
    return cur.fetchall()


def get_last_transaction(conn: sqlite3.Connection, user_id: int):
    """Última transacción del usuario o None."""
    cur = conn.execute(
        """
        SELECT id, date, description, category, payment_method, type, amount, currency
        FROM transactions
        WHERE user_id = ?
        ORDER BY id DESC
        LIMIT 1
        """,
        (user_id,),
    )
    return cur.fetchone()


def delete_transaction_by_id(conn: sqlite3.Connection, tx_id: int) -> None:
    """Elimina una transacción por id."""
    conn.execute("DELETE FROM transactions WHERE id = ?", (tx_id,))


def update_transaction_amount(
    conn: sqlite3.Connection, tx_id: int, new_amount: float
) -> None:
    """Actualiza el monto de una transacción."""
    conn.execute("UPDATE transactions SET amount = ? WHERE id = ?", (new_amount, tx_id))


def update_transaction_category(
    conn: sqlite3.Connection, tx_id: int, category: str
) -> None:
    """Actualiza la categoría de una transacción."""
    conn.execute("UPDATE transactions SET category = ? WHERE id = ?", (category, tx_id))


def upsert_budget(
    conn: sqlite3.Connection,
    user_id: int,
    category: str,
    amount: float,
    currency: str = "CAD",
) -> None:
    """Crea o actualiza el presupuesto de una categoría para el usuario."""
    conn.execute(
        """
        INSERT INTO budgets(user_id, category, amount, currency)
        VALUES(?, ?, ?, ?)
        ON CONFLICT(user_id, category) DO UPDATE SET
            amount = excluded.amount,
            currency = excluded.currency
        """,
        (user_id, category, amount, currency),
    )


def get_budget(conn: sqlite3.Connection, user_id: int, category: str):
    """Obtiene el presupuesto de una categoría o None."""
    cur = conn.execute(
        "SELECT category, amount, currency FROM budgets WHERE user_id = ? AND category = ?",
        (user_id, category),
    )
    return cur.fetchone()


def get_budgets(conn: sqlite3.Connection, user_id: int) -> list:
    """Obtiene todos los presupuestos del usuario."""
    cur = conn.execute(
        "SELECT category, amount, currency FROM budgets WHERE user_id = ? ORDER BY category",
        (user_id,),
    )
    return cur.fetchall()


def delete_budget(conn: sqlite3.Connection, user_id: int, category: str) -> None:
    """Elimina el presupuesto de una categoría."""
    conn.execute("DELETE FROM budgets WHERE user_id = ? AND category = ?", (user_id, category))


def get_budget_alert_level(
    conn: sqlite3.Connection, user_id: int, category: str, month: str
) -> int:
    """Obtiene el nivel de alerta guardado (0, 1 o 2). Devuelve 0 si no hay fila."""
    cur = conn.execute(
        "SELECT level FROM budget_alert_state WHERE user_id = ? AND category = ? AND month = ?",
        (user_id, category, month),
    )
    row = cur.fetchone()
    return int(row[0]) if row else 0


def upsert_budget_alert_level(
    conn: sqlite3.Connection,
    user_id: int,
    category: str,
    month: str,
    level: int,
) -> None:
    """Crea o actualiza el nivel de alerta para (user_id, category, month)."""
    conn.execute(
        """
        INSERT INTO budget_alert_state(user_id, category, month, level)
        VALUES(?, ?, ?, ?)
        ON CONFLICT(user_id, category, month) DO UPDATE SET level = excluded.level
        """,
        (user_id, category, month, level),
    )


def delete_transactions_for_month(
    conn: sqlite3.Connection, user_id: int, start: str, end: str
) -> int:
    """Elimina transacciones del usuario en el rango [start, end). Devuelve cantidad eliminada."""
    cur = conn.execute(
        "DELETE FROM transactions WHERE user_id = ? AND date >= ? AND date < ?",
        (user_id, start, end),
    )
    return cur.rowcount


def delete_budget_alert_state_for_month(
    conn: sqlite3.Connection, user_id: int, month: str
) -> int:
    """Elimina estado de alertas del usuario para el mes. Devuelve cantidad eliminada."""
    cur = conn.execute(
        "DELETE FROM budget_alert_state WHERE user_id = ? AND month = ?",
        (user_id, month),
    )
    return cur.rowcount


def get_income_expense_for_date(
    conn: sqlite3.Connection, user_id: int, date_str: str
) -> tuple[float, float]:
    """Ingresos y gastos del usuario para una fecha (YYYY-MM-DD). Devuelve (income, expense)."""
    cur = conn.execute(
        """
        SELECT type, SUM(amount)
        FROM transactions
        WHERE user_id = ? AND date = ?
        GROUP BY type
        """,
        (user_id, date_str),
    )
    income = 0.0
    expense = 0.0
    for row in cur.fetchall():
        t = (row[0] or "").upper().strip()
        amt = float(row[1] or 0)
        if "INGRESO" in t:
            income += amt
        else:
            expense += amt
    return income, expense


def get_expense_by_category_for_month(
    conn: sqlite3.Connection, user_id: int, start: str, end: str
) -> dict:
    """
    Gasto por categoría en el rango de fechas.
    Solo transacciones con type = 'EGRESO'.
    """
    cur = conn.execute(
        """
        SELECT category, SUM(amount)
        FROM transactions
        WHERE user_id = ?
          AND date >= ? AND date < ?
          AND UPPER(TRIM(COALESCE(type, ''))) = 'EGRESO'
        GROUP BY category
        """,
        (user_id, start, end),
    )
    return {row[0] or "SIN CATEGORIA": float(row[1] or 0) for row in cur.fetchall()}
