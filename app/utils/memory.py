import redis
from app.config import REDIS_URL
from app.utils.logging import log_error, log

# FIX CLAUDE: Membuat koneksi pool ke Redis dengan Auto-Healing (Anti-Putus)
try:
    redis_client = redis.from_url(
        REDIS_URL, 
        decode_responses=True,
        retry_on_timeout=True,      # Auto retry jika terjadi timeout
        socket_keepalive=True,      # Jaga koneksi TCP tetap hidup
        health_check_interval=30    # Ping Redis setiap 30 detik untuk cek detak jantung
    )
    redis_client.ping()
    log("🧠 Redis Engine V3.0 Connected (Auto-Healing Enabled)!")
except Exception as e:
    log_error("Redis Connection ERROR", e)
    redis_client = None

def set_tick(symbol: str, price: float):
    if redis_client:
        try:
            # Menyimpan harga ke Redis RAM. Contoh key: "tick:BTC/USDT:USDT"
            redis_client.set(f"tick:{symbol}", float(price))
        except Exception:
            pass

def get_tick(symbol: str):
    if redis_client:
        try:
            val = redis_client.get(f"tick:{symbol}")
            return float(val) if val else None
        except Exception:
            return None
    return None
