import redis
from app.config import REDIS_URL
from app.utils.logging import log_error, log

try:
    redis_client = redis.from_url(REDIS_URL, decode_responses=True, retry_on_timeout=True, socket_keepalive=True, health_check_interval=30)
    redis_client.ping()
    log("🧠 Redis Engine Connected!")
except Exception as e:
    log_error("Redis Connection ERROR", e)
    redis_client = None

def set_tick(symbol: str, price: float):
    if redis_client:
        try: redis_client.set(f"tick:{symbol}", float(price))
        except: pass

def get_tick(symbol: str):
    if redis_client:
        try:
            val = redis_client.get(f"tick:{symbol}")
            return float(val) if val else None
        except: return None
    return None
