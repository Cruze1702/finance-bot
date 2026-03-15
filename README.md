# Finance Bot

A standalone Telegram bot for personal finance tracking: log transactions in natural language, manage per-category budgets, view monthly stats, and export Excel reports.

## Features

- **Natural-language transactions** — `Uber 150 debito`, `Costco 120 credito`, `Ingreso 2500 sueldo`
- **Stats & summaries** — monthly income, expenses, balance, top categories
- **Budgets** — per-category limits with automatic 80% / 100% alerts
- **Excel export** — monthly reports (template-based or clean format)
- **Weekly digest** — optional Sunday morning report for subscribers
- **Multi-user** — supports multiple users (configurable via `USER_MAP`)

## Folder Structure

```
├── telegram_bot.py              # Bot entrypoint (Telegram polling)
├── app/
│   ├── agents/admin/            # Core finance logic
│   │   ├── models.py            # Constants, paths, categories
│   │   ├── parser.py            # Text → amount, category, payment
│   │   ├── repositories.py      # SQLite data access
│   │   ├── service.py           # Use cases (transactions, budgets, reports)
│   │   ├── stats.py             # Statistics computation & formatting
│   │   ├── excel.py             # Excel report generation
│   │   └── main.py              # CLI entrypoint
│   └── templates/
│       └── Plantilla_Presupuesto_Dashboard_SIMPLE.xlsx
├── storage/                     # Runtime data (auto-created)
│   ├── admin.sqlite             # SQLite DB
│   └── subscribers.json         # Weekly report subscribers
├── reports/                     # Generated Excel files (auto-created)
├── requirements.txt
├── .env.example
└── .gitignore
```

## Setup

1. **Clone and create virtual environment**

   ```bash
   python -m venv venv
   source venv/bin/activate   # Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

2. **Get a Telegram bot token**

   - Open [@BotFather](https://t.me/BotFather) on Telegram
   - Send `/newbot` and follow the prompts
   - Copy the token (e.g. `123456789:ABCdefGHIjklMNOpqrsTUVwxyz`)

3. **Configure environment**

   ```bash
   cp .env.example .env
   # Edit .env and set BOT_TOKEN=your_token_here
   ```

   Or export directly:

   ```bash
   export BOT_TOKEN=your_token_here
   ```

   To load from `.env` before running: `export $(grep -v '^#' .env | xargs)` (Linux/macOS).

## Run

### Bot (Telegram)

From the project root:

```bash
python telegram_bot.py
```

Or with explicit env:

```bash
BOT_TOKEN=your_token_here python telegram_bot.py
```

### Admin CLI (no Telegram)

For adding transactions or generating Excel from the command line:

```bash
python -m app.agents.admin.main add cross "Uber 25 debito"
python -m app.agents.admin.main resumen
python -m app.agents.admin.main excel
python -m app.agents.admin.main movimientos
```

## Basic Commands (Telegram)

| Command / Text | Description |
|----------------|-------------|
| `/start` | Help and usage |
| `/whoami` | Show detected user |
| `/stats` or `stats` | Monthly stats |
| `/summary` or `summary` | Financial summary |
| `/excel` or `excel` | Export Excel for current month |
| `/last` | Last 5 transactions |
| `/budgets` | List budgets and status |
| `/subscribe` | Weekly report (Sunday 09:00) |
| `/unsubscribe` | Stop weekly report |
| `Uber 150 debito` | Add expense |
| `Ingreso 2500 sueldo` | Add income |
| `last` | Show last transactions |
| `delete last` | Delete last transaction |
| `edit last 120` | Edit last transaction amount |
| `budget comida 500` | Set budget for category |
| `budgets` | List budgets |
| `delete budget comida` | Remove budget |
| `reset month` | Clear current month data |

## Runtime Files

| Path | Created | Purpose |
|------|---------|---------|
| `storage/` | On first run | Directory for DB and subscribers |
| `storage/admin.sqlite` | On first transaction | SQLite DB |
| `storage/subscribers.json` | On first run | Weekly report chat IDs |
| `reports/` | On Excel export | Generated `.xlsx` files |
| `app/templates/Plantilla_*.xlsx` | Shipped with repo | Excel template (template-based export) |

If the template is missing, the template-based Excel export fails. Use `movimientos` (admin CLI) for a clean export without the template.

## Requirements

- Python 3.10+
- `python-telegram-bot>=20,<22`
- `openpyxl>=3.1`

## Deployment Notes

### Environment

The only required environment variable is `BOT_TOKEN`. The bot validates it at startup and exits with a clear error if missing.

### Persistent data

Back up or preserve these across deploys:

| Path | Contents |
|------|----------|
| `storage/admin.sqlite` | All transactions, users, budgets, alert state |
| `storage/subscribers.json` | Weekly report subscriber list |

`reports/` contains generated Excel files and can be treated as ephemeral.

---

## Server Deployment (Hetzner / any Linux VPS)

The bot uses **long-polling** (not webhooks), so it works behind NAT without exposing any ports.

### 1. Provision the server

Any Debian/Ubuntu VPS works. A **CX22** (2 vCPU / 4 GB) on Hetzner is more than enough.

```bash
# SSH into your VPS
ssh root@<your-vps-ip>

# Create a dedicated service user (no login shell)
sudo useradd -r -s /usr/sbin/nologin finance-bot
```

### 2. Clone the repo

```bash
sudo mkdir -p /opt/finance-bot-foxy
cd /opt/finance-bot-foxy
sudo git clone https://github.com/<you>/finance-bot-foxy.git .
sudo chown -R finance-bot:finance-bot /opt/finance-bot-foxy
```

### 3. Create the virtual environment and install dependencies

```bash
cd /opt/finance-bot-foxy
sudo -u finance-bot python3 -m venv venv
sudo -u finance-bot venv/bin/pip install --upgrade pip
sudo -u finance-bot venv/bin/pip install -r requirements.txt
```

### 4. Set the BOT_TOKEN

```bash
sudo cp .env.example .env
sudo nano .env        # paste your real token
sudo chown finance-bot:finance-bot .env
sudo chmod 600 .env   # readable only by the service user
```

The `.env` file is loaded by systemd via `EnvironmentFile=`, so there is no need for `python-dotenv`.

### 5. Create runtime directories

```bash
sudo -u finance-bot mkdir -p storage reports
```

### 6. Install the systemd service

A ready-made unit file is included in the repo (`finance-bot.service`).

```bash
sudo cp finance-bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable finance-bot   # start on boot
sudo systemctl start finance-bot
```

Verify it is running:

```bash
sudo systemctl status finance-bot
```

### 7. View logs

All bot output goes to the systemd journal:

```bash
# Live tail
journalctl -u finance-bot -f

# Last 100 lines
journalctl -u finance-bot -n 100

# Since last boot
journalctl -u finance-bot -b
```

### 8. Updating the bot

```bash
cd /opt/finance-bot-foxy
sudo -u finance-bot git pull
sudo -u finance-bot venv/bin/pip install -r requirements.txt
sudo systemctl restart finance-bot
journalctl -u finance-bot -f   # verify clean startup
```

### systemd service reference

See `finance-bot.service` in the repo root. Key properties:

| Directive | Value | Purpose |
|-----------|-------|---------|
| `Type` | `simple` | Bot runs in the foreground |
| `EnvironmentFile` | `/opt/finance-bot-foxy/.env` | Loads `BOT_TOKEN` securely |
| `Restart` | `on-failure` | Auto-restart on crash |
| `RestartSec` | `5` | Wait 5 s before restart |
| `StartLimitBurst` | `5` | Max 5 restarts per interval |
| `StartLimitIntervalSec` | `60` | …within 60 s, then stop trying |
| `ProtectSystem` | `strict` | Read-only filesystem except allowed paths |
| `ReadWritePaths` | `storage/ reports/` | Only dirs the bot writes to |
| `NoNewPrivileges` | `true` | Cannot escalate privileges |

### Quick start (tmux / screen)

If you prefer not to use systemd:

```bash
ssh user@<your-vps-ip>
cd /opt/finance-bot-foxy
source venv/bin/activate
export $(grep -v '^#' .env | xargs)
python telegram_bot.py
```

### Deployment risks & notes

| Risk | Mitigation |
|------|------------|
| **SQLite under concurrent writes** | Single-user bot; not an issue. If multi-user load grows, consider WAL mode or PostgreSQL. |
| **No backup automation** | Schedule a cron job: `cp storage/admin.sqlite storage/admin.sqlite.bak` or use Hetzner snapshots. |
| **Token in `.env` on disk** | File permissions `600` + dedicated user limit exposure. Never commit `.env`. |
| **Telegram API rate limits** | Long-polling + low traffic makes this unlikely. No mitigation needed now. |
| **Python/pip updates** | Pin Python minor version on the VPS; use `venv` to isolate. |
| **No health check** | systemd `Restart=on-failure` covers crashes. For deeper monitoring, add an HTTP health endpoint later. |
| **`ProtectHome=true`** | The service cannot read `/home`. Deploy to `/opt/` as documented, not `~`. |
