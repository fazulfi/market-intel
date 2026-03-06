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

ALERT_COOLDOWN_SEC = int(os.getenv("ALERT_COOLDOWN_SEC", 300))
ENABLE_COMBO_ONLY = os.getenv("ENABLE_COMBO_ONLY", "true").lower() == "true"

ATR_N = int(os.getenv("ATR_N", 14))
ATR_WARMUP = int(os.getenv("ATR_WARMUP", 120))
ATR_SL_MULT = float(os.getenv("ATR_SL_MULT", 1.0))
RR_TP = float(os.getenv("RR_TP", 2.0))

# --- V1.6 ---
ENABLE_TRADES = os.getenv("ENABLE_TRADES", "true").lower() == "true"
TRADE_MANAGER_INTERVAL_SEC = int(os.getenv("TRADE_MANAGER_INTERVAL_SEC", 5))
CLOSE_RULE = os.getenv("CLOSE_RULE", "conservative").lower()

# --- V1.7 SUMMARY FIX ---
SUMMARY_HOURLY_MINUTE = int(os.getenv("SUMMARY_HOURLY_MINUTE", "0"))
SUMMARY_DAILY_HOUR = int(os.getenv("SUMMARY_DAILY_HOUR", "0"))
SUMMARY_DAILY_MINUTE = int(os.getenv("SUMMARY_DAILY_MINUTE", "5"))

# --- V1.8 EMA + RETEST ---
EMA_TREND_N = int(os.getenv("EMA_TREND_N", 200))
EMA_TREND_TF = os.getenv("EMA_TREND_TF", "15m")
ENABLE_RETEST = os.getenv("ENABLE_RETEST", "true").lower() == "true"
RETEST_MAX_BARS = int(os.getenv("RETEST_MAX_BARS", 6))
RETEST_TOUCH_MODE = os.getenv("RETEST_TOUCH_MODE", "wick").lower()

# --- V1.9 WS + TF MAP ---
ENABLE_WS_TICKER = os.getenv("ENABLE_WS_TICKER", "true").lower() == "true"
WS_MARKET_TYPE = os.getenv("WS_MARKET_TYPE", "linear").lower()
WS_PING_SEC = int(os.getenv("WS_PING_SEC", 20))
WS_RECONNECT_SEC = int(os.getenv("WS_RECONNECT_SEC", 3))

def _parse_tf_map(raw: str):
    # format: "1m:5m,5m:15m,15m:1h"
    out = {}
    for part in (raw or "").split(","):
        part = part.strip()
        if not part or ":" not in part:
            continue
        k, v = part.split(":", 1)
        out[k.strip()] = v.strip()
    return out

TREND_TF_MAP = _parse_tf_map(os.getenv("TREND_TF_MAP", "1m:15m,5m:1h,15m:4h"))
ATR_TF_MAP = _parse_tf_map(os.getenv("ATR_TF_MAP", "1m:5m,5m:15m,15m:1h"))

# --- WS HYBRID ---
ENABLE_WS_KLINES = os.getenv("ENABLE_WS_KLINES", "true").lower() == "true"
ENABLE_REST_COLLECTOR = os.getenv("ENABLE_REST_COLLECTOR", "false").lower() == "true"
BYBIT_WS_PUBLIC_URL = os.getenv("BYBIT_WS_PUBLIC_URL", "wss://stream.bybit.com/v5/public/linear")

def _csv_fallback(name, fallback):
    raw = os.getenv(name, "")
    xs = [x.strip() for x in raw.split(",") if x.strip()]
    return xs or fallback

WS_KLINE_TIMEFRAMES = _csv_fallback("WS_KLINE_TIMEFRAMES", ["1m","5m","15m","1h","4h"])

# --- V2.3 TWO-STEP ENTRY ---
ENTRY1_SIZE = float(os.getenv("ENTRY1_SIZE", 0.30))
ENTRY2_SIZE = float(os.getenv("ENTRY2_SIZE", 0.70))
ENABLE_ENTRY2 = os.getenv("ENABLE_ENTRY2", "true").lower() == "true"
ENTRY2_ATR_MULT = float(os.getenv("ENTRY2_ATR_MULT", 1.0))

POST_CLOSE_COOLDOWN_SEC = int(os.getenv("POST_CLOSE_COOLDOWN_SEC", 300))

# --- V2.3.1 POST-CLOSE COOLDOWN BY BARS ---
POST_CLOSE_COOLDOWN_BARS = int(os.getenv("POST_CLOSE_COOLDOWN_BARS", 2))

# --- V2.4 LAYERED SETUP ---
TP1_ATR_MULT = float(os.getenv("TP1_ATR_MULT", 1.0))
TP2_ATR_MULT = float(os.getenv("TP2_ATR_MULT", 1.8))
TP3_ATR_MULT = float(os.getenv("TP3_ATR_MULT", 2.4))
SL_ATR_MULT = float(os.getenv("SL_ATR_MULT", 2.0))
ENTRY1_ATR_OFFSET = float(os.getenv("ENTRY1_ATR_OFFSET", 0.0))
ENTRY2_ATR_OFFSET = float(os.getenv("ENTRY2_ATR_OFFSET", 1.0))
SETUP_EXPIRY_BARS = int(os.getenv("SETUP_EXPIRY_BARS", 12))
