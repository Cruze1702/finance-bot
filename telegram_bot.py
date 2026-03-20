import re
import sys
import json
import logging
from datetime import datetime, time as dtime

from app.agents.admin.models import (
    DEFAULT_USER,
    INCOME_HINTS,
    REPORTS_DIR as _REPORTS_DIR,
    STORAGE_DIR,
    TZ,
    USER_MAP,
    USERS,
)
from app.agents.admin.service import (
    add_transaction,
    check_budget_alert,
    delete_budget_for_category,
    delete_last_transaction,
    edit_last_transaction_amount,
    export_excel_template,
    get_budget_status,
    get_summary,
    get_weekly_report,
    list_budgets_status,
    list_last_transactions,
    reset_month_data,
    set_budget,
)
from app.agents.admin.stats import compute_stats, compute_stats_all, format_stats
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
    Defaults,
)

import os

TOKEN = os.getenv("BOT_TOKEN")

REPORTS_DIR = _REPORTS_DIR
SUBS_FILE = STORAGE_DIR / "subscribers.json"

# Weekly report schedule: Sunday 09:00 PST
WEEKLY_TIME = dtime(9, 0)
WEEKLY_DAY = 6  # 0=Mon ... 6=Sun

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger("telegram_finance_bot")

HELP_TEXT = (
    "👋 *Finance Bot*\n\n"
    "✅ Escribe natural:\n"
    "• `Uber 150 debito`\n"
    "• `Costco 120 credito`\n"
    "• `Ingreso 2500 sueldo`\n\n"
    "Comandos:\n"
    "• `stats` o `/stats`\n"
    "• `excel` o `/excel`\n"
    "• `/whoami`\n"
    "• `/subscribe` (reporte semanal)\n"
    "• `/unsubscribe`\n"
)

def ensure_files():
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    if not SUBS_FILE.exists():
        SUBS_FILE.write_text(json.dumps({"subscribers": []}, indent=2), encoding="utf-8")


def load_subs() -> list[int]:
    ensure_files()
    try:
        data = json.loads(SUBS_FILE.read_text(encoding="utf-8"))
        subs = data.get("subscribers", [])
        return sorted(list(set(int(x) for x in subs)))
    except Exception:
        return []


def save_subs(subs: list[int]) -> None:
    ensure_files()
    SUBS_FILE.write_text(json.dumps({"subscribers": sorted(list(set(subs)))}, indent=2), encoding="utf-8")


def resolve_user(update: Update) -> str:
    tg_username = (update.effective_user.username or "").strip().lower()
    if tg_username in USER_MAP:
        return USER_MAP[tg_username]

    first = (update.effective_user.first_name or "").strip().lower()
    if "pau" in first:
        return "pau"

    return DEFAULT_USER


def current_month() -> str:
    return datetime.now(TZ).strftime("%Y-%m")


def normalize_month(m: str | None) -> str | None:
    if not m:
        return None
    m = m.strip()
    return m if re.fullmatch(r"\d{4}-\d{2}", m) else None


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(HELP_TEXT, parse_mode=ParseMode.MARKDOWN)


async def cmd_whoami(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    resolved = resolve_user(update)
    username = f"@{u.username}" if u.username else "(sin username)"
    msg = (
        "🧾 Tu Telegram\n"
        f"- first_name: {u.first_name}\n"
        f"- username: {username}\n"
        f"- detectado como: {resolved}\n"
    )
    await update.message.reply_text(msg)


async def cmd_subscribe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    subs = load_subs()
    chat_id = update.effective_chat.id
    if chat_id not in subs:
        subs.append(chat_id)
        save_subs(subs)
    await update.message.reply_text("✅ Suscrito. Te mandaré reporte semanal (Domingo 09:00).")


async def cmd_unsubscribe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    subs = load_subs()
    chat_id = update.effective_chat.id
    subs = [x for x in subs if x != chat_id]
    save_subs(subs)
    await update.message.reply_text("🛑 Listo. Ya no te mandaré el reporte semanal.")


async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    parts = (update.message.text or "").strip().split()
    m = normalize_month(parts[1]) if len(parts) >= 2 else current_month()
    user = resolve_user(update)
    display_name = USERS.get(user, user)
    try:
        st_personal = compute_stats(display_name, m)
        st_all = compute_stats_all(m)
        msg = format_stats(st_personal) + "\n\n---\n\n" + format_stats(st_all)
        await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        await update.message.reply_text(f"❌ No pude generar stats:\n{e}")


async def cmd_last(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = resolve_user(update)
    display_name = USERS.get(user, user)
    result = list_last_transactions(display_name)
    await update.message.reply_text(result["message"])


async def cmd_budgets(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = resolve_user(update)
    display_name = USERS.get(user, user)
    result = list_budgets_status(display_name)
    await update.message.reply_text(result["message"])


async def cmd_summary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = resolve_user(update)
    display_name = USERS.get(user, user)
    m = current_month()
    today_str = datetime.now(TZ).strftime("%Y-%m-%d")
    result = get_summary(display_name, month=m, today_str=today_str)
    await update.message.reply_text(result["message"])


async def cmd_reset_month(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = resolve_user(update)
    display_name = USERS.get(user, user)
    result = reset_month_data(display_name)
    await update.message.reply_text(result["message"])


async def cmd_excel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    parts = (update.message.text or "").strip().split()
    m = normalize_month(parts[1]) if len(parts) >= 2 else current_month()

    try:
        path = export_excel_template(month=m)
    except Exception as e:
        log.exception("Excel generation failed: %s", e)
        await update.message.reply_text(f"❌ No pude generar Excel:\n{e}")
        return

    if path is None or not path.exists():
        await update.message.reply_text("❌ No pude generar Excel. Verifica que la plantilla exista en app/templates/.")
        return

    await update.message.reply_document(
        path.open("rb"), filename=path.name, caption=f"📎 Excel {m}"
    )


def has_amount(text: str) -> bool:
    return re.search(r"\d+(\.\d+)?", text) is not None


def looks_like_income(text: str) -> bool:
    """Usa INCOME_HINTS centralizado de models."""
    t = text.lower()
    if t.startswith("ingreso"):
        return True
    for h in INCOME_HINTS:
        if h in t:
            return True
    return False


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()
    if not text:
        return

    low = text.lower().strip()

    if low == "last" or low == "delete last" or low.startswith("edit last "):
        user = resolve_user(update)
        display_name = USERS.get(user, user)
        if low == "last":
            result = list_last_transactions(display_name)
            await update.message.reply_text(result["message"])
        elif low == "delete last":
            result = delete_last_transaction(display_name)
            await update.message.reply_text(result["message"])
        else:
            parts = text.split(maxsplit=2)
            if len(parts) >= 3:
                try:
                    amt = float(parts[2])
                    if amt > 0:
                        result = edit_last_transaction_amount(display_name, amt)
                        await update.message.reply_text(result["message"])
                    else:
                        await update.message.reply_text("❌ El monto debe ser mayor a 0.")
                except ValueError:
                    await update.message.reply_text("❌ Monto inválido. Ej: edit last 120")
            else:
                await update.message.reply_text("❌ Uso: edit last <monto>")
        return

    if low == "budgets":
        user = resolve_user(update)
        display_name = USERS.get(user, user)
        result = list_budgets_status(display_name)
        await update.message.reply_text(result["message"])
        return

    if low.startswith("delete budget "):
        parts = text.split(maxsplit=2)
        if len(parts) >= 3:
            user = resolve_user(update)
            display_name = USERS.get(user, user)
            result = delete_budget_for_category(display_name, parts[2])
            await update.message.reply_text(result["message"])
        else:
            await update.message.reply_text("❌ Uso: delete budget <categoría>")
        return

    if low.startswith("budget "):
        parts = text.split(maxsplit=2)
        if len(parts) >= 2:
            user = resolve_user(update)
            display_name = USERS.get(user, user)
            cat_input = parts[1]
            if len(parts) >= 3:
                try:
                    amt = float(parts[2])
                    if amt > 0:
                        result = set_budget(display_name, cat_input, amt)
                        await update.message.reply_text(result["message"])
                    else:
                        await update.message.reply_text("❌ El monto debe ser mayor a 0.")
                except ValueError:
                    await update.message.reply_text("❌ Monto inválido. Ej: budget comida 500")
            else:
                result = get_budget_status(display_name, cat_input)
                await update.message.reply_text(result["message"])
        else:
            await update.message.reply_text("❌ Uso: budget <categoría> [monto]")
        return

    if low == "stats":
        await cmd_stats(update, context)
        return
    if low == "summary":
        await cmd_summary(update, context)
        return
    if low == "excel":
        await cmd_excel(update, context)
        return
    if low == "subscribe":
        await cmd_subscribe(update, context)
        return
    if low == "unsubscribe":
        await cmd_unsubscribe(update, context)
        return

    if low == "reset month":
        user = resolve_user(update)
        display_name = USERS.get(user, user)
        result = reset_month_data(display_name)
        await update.message.reply_text(result["message"])
        return

    if not has_amount(text):
        await update.message.reply_text(
            "❌ No detecté un monto en tu mensaje.\n\n"
            "Ejemplos:\n"
            "• uber 150 debito\n"
            "• comida 80\n"
            "• salario 2500\n"
            "• me pagaron 800 freelance"
        )
        return

    user = resolve_user(update)

    if looks_like_income(text) and not low.startswith("ingreso"):
        final_text = "ingreso " + text
    elif (not looks_like_income(text)) and not low.startswith("gasto"):
        final_text = "gasto " + text
    else:
        final_text = text

    display_name = USERS.get(user, user)
    result = add_transaction(display_name, final_text)
    msg = result["message"]
    if result["success"] and result["type"] == "EGRESO":
        alert = check_budget_alert(display_name, result["category"])
        if alert:
            msg = msg + "\n\n" + alert["message"]
    await update.message.reply_text(msg)


async def weekly_report_job(context: ContextTypes.DEFAULT_TYPE):
    subs = load_subs()
    if not subs:
        return

    m = current_month()
    today_str = datetime.now(TZ).strftime("%Y-%m-%d")

    for chat_id in subs:
        try:
            result_cross = get_weekly_report("Cross", month=m, today_str=today_str)
            await context.bot.send_message(chat_id=chat_id, text=result_cross["message"])

            result_pau = get_weekly_report("Pau", month=m, today_str=today_str)
            st_pau = compute_stats("pau", m)
            if st_pau["income"] != 0 or st_pau["expense"] != 0:
                await context.bot.send_message(chat_id=chat_id, text=result_pau["message"])
        except Exception as e:
            log.exception("weekly report error: %s", e)


async def error_handler(update, context):
    log.exception("Unhandled error: %s", context.error)
    try:
        if update and update.effective_message:
            await update.effective_message.reply_text(
                "⚠️ Ocurrió un error procesando tu mensaje. Intenta nuevamente."
            )
    except Exception:
        pass


def main():
    if not TOKEN or not str(TOKEN).strip():
        log.error(
            "BOT_TOKEN is not set. Set it with: export BOT_TOKEN=your_token\n"
            "Get a token from @BotFather: https://t.me/BotFather"
        )
        sys.exit(1)

    ensure_files()

    defaults = Defaults(tzinfo=TZ)
    app = ApplicationBuilder().token(TOKEN).defaults(defaults).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("whoami", cmd_whoami))
    app.add_handler(CommandHandler("subscribe", cmd_subscribe))
    app.add_handler(CommandHandler("unsubscribe", cmd_unsubscribe))
    app.add_handler(CommandHandler("stats", cmd_stats))
    app.add_handler(CommandHandler("excel", cmd_excel))
    app.add_handler(CommandHandler("last", cmd_last))
    app.add_handler(CommandHandler("budgets", cmd_budgets))
    app.add_handler(CommandHandler("summary", cmd_summary))
    app.add_handler(CommandHandler("reset_month", cmd_reset_month))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    app.add_error_handler(error_handler)

    if app.job_queue:
        app.job_queue.run_daily(
            weekly_report_job,
            time=WEEKLY_TIME,
            days=(WEEKLY_DAY,),
            name="weekly_report",
        )
        log.info("Weekly report job scheduled (Sunday 09:00 PST).")

    log.info("Bot started, polling...")
    app.run_polling(close_loop=False)


if __name__ == "__main__":
    main()
