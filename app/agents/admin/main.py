"""
CLI entrypoint for the finance bot.
Parses arguments and dispatches to service / excel.
"""
import sys

from app.agents.admin.models import USERS
from app.agents.admin import service


def main() -> None:
    if len(sys.argv) < 2:
        print("Comandos:")
        print("add <cross|pau> <texto>")
        print("resumen [cross|pau]")
        print("excel           (usa plantilla)")
        print("movimientos     (excel limpio)")
        return

    cmd = sys.argv[1]

    if cmd == "add":
        if len(sys.argv) < 4:
            print("Uso: add <cross|pau> <texto>")
            return
        user_key = sys.argv[2].lower()
        if user_key not in USERS:
            print("Usuario inválido")
            return
        user = USERS[user_key]
        text = " ".join(sys.argv[3:])
        service.add_transaction(user, text)
        return

    if cmd == "resumen":
        user = None
        if len(sys.argv) >= 3:
            user = USERS.get(sys.argv[2].lower())
        service.resumen_mes(user)
        return

    if cmd == "excel":
        service.export_excel_template()
        return

    if cmd == "movimientos":
        service.export_movimientos()
        return

    print("Comando no reconocido. Usa: add, resumen, excel, movimientos")


if __name__ == "__main__":
    main()
