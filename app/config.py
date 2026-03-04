import os

def _csv(name):
    raw = os.getenv(name, "")
    return [x.strip() for x in raw.split(",") if x.strip()]

EXCHANGE = os.getenv("EXCHANGE", "bybit")

SYMBOLS = _csv("SYMBOLS")
TIMEFRAMES = _csv("TIMEFRAMES") or ["1m", "5m"]

COLLECTOR_INTERVAL_SEC = int(os.getenv("COLLECTOR_INTERVAL_SEC", 20))
SIGNAL_INTERVAL_SEC = int(os.getenv("SIGNAL_INTERVAL_SEC", 30))
HEARTBEAT_INTERVAL_SEC = int(os.getenv("HEARTBEAT_INTERVAL_SEC", 60))

BREAKOUT_N = int(os.getenv("BREAKOUT_N", 20))
VOL_AVG_N = int(os.getenv("VOL_AVG_N", 20))
VOL_SPIKE_K = float(os.getenv("VOL_SPIKE_K", 2.5))

BACKFILL_ON_START = os.getenv("BACKFILL_ON_START", "false").lower() == "true"
BACKFILL_LIMIT = int(os.getenv("BACKFILL_LIMIT", 1000))

POSTGRES_HOST = os.getenv("POSTGRES_HOST", "db")
POSTGRES_PORT = os.getenv("POSTGRES_PORT", "5432")
POSTGRES_DB = os.getenv("POSTGRES_DB", "marketintel")
POSTGRES_USER = os.getenv("POSTGRES_USER", "marketintel")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "marketintel")

DB_DSN = (
    f"host={POSTGRES_HOST} port={POSTGRES_PORT} "
    f"dbname={POSTGRES_DB} user={POSTGRES_USER} password={POSTGRES_PASSWORD}"
)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

VOL_SPIKE_K = float(os.getenv("VOL_SPIKE_K", 2.0))

# --- V1.4 ---
ALERT_COOLDOWN_SEC = int(os.getenv("ALERT_COOLDOWN_SEC", 300))
ENABLE_COMBO_SIGNAL = os.getenv("ENABLE_COMBO_SIGNAL", "true").lower() == "true"
