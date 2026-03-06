from app.config import *
from app.utils.logging import log
from app.utils.logging import log_error

def collect_loop(repo, ex, shutdown_event):
    if not ENABLE_REST_COLLECTOR:
        log("REST Collector disabled (WS mode ON)")
        return
        
    while not shutdown_event.is_set():

        try:
            for s in SYMBOLS:
                for tf in TIMEFRAMES:
                    candles = ex.fetch_ohlcv(s, tf, limit=200)
                    repo.upsert_candles(EXCHANGE, s, tf, candles)
        except Exception as e:
            log_error("Collector ERROR", e)

        shutdown_event.wait(COLLECTOR_INTERVAL_SEC)
