import os
from pathlib import Path

def _csv(name):
    raw = os.getenv(name, "")
    return [x.strip() for x in raw.split(",") if x.strip()]

def _normalize_symbols(items):
    seen = set()
    out = []
    for item in items:
        s = item.strip().upper()
        if not s or s.startswith("#"): continue
        if s not in seen:
            seen.add(s)
            out.append(s)
    return out

def _load_symbols():
    symbols_file = os.getenv("SYMBOLS_FILE", "/workspace/tickers.txt")
    path = Path(symbols_file)
    if path.exists():
        symbols = _normalize_symbols(path.read_text(encoding="utf-8").splitlines())
        if not symbols: raise ValueError(f"No symbols found in {symbols_file}")
        return symbols
    fallback = _normalize_symbols(_csv("SYMBOLS"))
    return fallback or ["BTC/USDT:USDT"]

EXCHANGE = os.getenv("EXCHANGE", "bybit")
SYMBOLS = _load_symbols()
TIMEFRAMES = _csv("TIMEFRAMES") or ["1m", "5m"]

COLLECTOR_INTERVAL_SEC = int(os.getenv("COLLECTOR_INTERVAL_SEC", 20))
SIGNAL_INTERVAL_SEC = int(os.getenv("SIGNAL_INTERVAL_SEC", 5))
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
DB_DSN = f"host={POSTGRES_HOST} port={POSTGRES_PORT} dbname={POSTGRES_DB} user={POSTGRES_USER} password={POSTGRES_PASSWORD}"

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
TELEGRAM_CHANNEL_ID = os.getenv('TELEGRAM_CHANNEL_ID')
ALERT_COOLDOWN_SEC = int(os.getenv("ALERT_COOLDOWN_SEC", 5))

ATR_N = int(os.getenv("ATR_N", 14))
ATR_WARMUP = int(os.getenv("ATR_WARMUP", 120))

ENABLE_TRADES = os.getenv("ENABLE_TRADES", "true").lower() == "true"
TRADE_MANAGER_INTERVAL_SEC = int(os.getenv("TRADE_MANAGER_INTERVAL_SEC", 5))

SUMMARY_HOURLY_MINUTE = int(os.getenv("SUMMARY_HOURLY_MINUTE", "0"))
SUMMARY_DAILY_HOUR = int(os.getenv("SUMMARY_DAILY_HOUR", "0"))
SUMMARY_DAILY_MINUTE = int(os.getenv("SUMMARY_DAILY_MINUTE", "5"))
SUMMARY_WEEKLY_DAY = int(os.getenv("SUMMARY_WEEKLY_DAY", "0"))
SUMMARY_WEEKLY_HOUR = int(os.getenv("SUMMARY_WEEKLY_HOUR", "0"))
SUMMARY_WEEKLY_MINUTE = int(os.getenv("SUMMARY_WEEKLY_MINUTE", "10"))

EMA_TREND_N = int(os.getenv("EMA_TREND_N", 200))
EMA_TREND_TF = os.getenv("EMA_TREND_TF", "15m")

ENABLE_WS_TICKER = os.getenv("ENABLE_WS_TICKER", "true").lower() == "true"
WS_MARKET_TYPE = os.getenv("WS_MARKET_TYPE", "linear").lower()
WS_PING_SEC = int(os.getenv("WS_PING_SEC", 20))
WS_RECONNECT_SEC = int(os.getenv("WS_RECONNECT_SEC", 3))

def _parse_tf_map(raw: str):
    out = {}
    for part in (raw or "").split(","):
        part = part.strip()
        if not part or ":" not in part: continue
        k, v = part.split(":", 1)
        out[k.strip()] = v.strip()
    return out

TREND_TF_MAP = _parse_tf_map(os.getenv("TREND_TF_MAP", "1m:15m,5m:1h,15m:4h"))
ATR_TF_MAP = _parse_tf_map(os.getenv("ATR_TF_MAP", "1m:5m,5m:15m,15m:1h"))

ENABLE_WS_KLINES = os.getenv("ENABLE_WS_KLINES", "true").lower() == "true"
ENABLE_REST_COLLECTOR = os.getenv("ENABLE_REST_COLLECTOR", "false").lower() == "true"
BYBIT_WS_PUBLIC_URL = os.getenv("BYBIT_WS_PUBLIC_URL", "wss://stream.bybit.com/v5/public/linear")

def _csv_fallback(name, fallback):
    raw = os.getenv(name, "")
    xs = [x.strip() for x in raw.split(",") if x.strip()]
    return xs or fallback

WS_KLINE_TIMEFRAMES = _csv_fallback("WS_KLINE_TIMEFRAMES", ["1m", "5m", "15m", "1h"])

ENTRY1_SIZE = float(os.getenv("ENTRY1_SIZE", 0.30))
ENTRY2_SIZE = float(os.getenv("ENTRY2_SIZE", 0.70))
POST_CLOSE_COOLDOWN_BARS = int(os.getenv("POST_CLOSE_COOLDOWN_BARS", 6))

TP1_ATR_MULT = float(os.getenv("TP1_ATR_MULT", 1.0))
TP2_ATR_MULT = float(os.getenv("TP2_ATR_MULT", 1.8))
TP3_ATR_MULT = float(os.getenv("TP3_ATR_MULT", 2.4))
SL_ATR_MULT = float(os.getenv("SL_ATR_MULT", 2.0))
ENTRY1_ATR_OFFSET = float(os.getenv("ENTRY1_ATR_OFFSET", 0.0))
ENTRY2_ATR_OFFSET = float(os.getenv("ENTRY2_ATR_OFFSET", 1.0))
SETUP_EXPIRY_BARS = int(os.getenv("SETUP_EXPIRY_BARS", 12))
ENTRY1_CHASE_ATR_PCT = float(os.getenv("ENTRY1_CHASE_ATR_PCT", 0.25))

TP1_CLOSE_PCT = float(os.getenv("TP1_CLOSE_PCT", 0.30))
TP2_CLOSE_PCT = float(os.getenv("TP2_CLOSE_PCT", 0.40))
TP3_CLOSE_PCT = float(os.getenv("TP3_CLOSE_PCT", 0.30))
MOVE_SL_TO_BE_AFTER_TP1 = os.getenv("MOVE_SL_TO_BE_AFTER_TP1", "true").lower() == "true"
MOVE_SL_TO_TP1_AFTER_TP2 = os.getenv("MOVE_SL_TO_TP1_AFTER_TP2", "true").lower() == "true"

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
ENABLE_SUMMARY = os.getenv('ENABLE_SUMMARY', 'true').lower() == 'true'

# --- V4.0 EXECUTION LAYER ---
BYBIT_API_KEY = os.getenv("BYBIT_API_KEY", "")
BYBIT_API_SECRET = os.getenv("BYBIT_API_SECRET", "")
DRY_RUN = os.getenv("DRY_RUN", "true").lower() == "true"

# --- V4.0 KILL SWITCH ---
EMERGENCY_STOP = os.getenv('EMERGENCY_STOP', 'false').lower() == 'true'
