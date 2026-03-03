from app.config import *
from app.utils.logging import log, log_error

def run_backfill(repo, ex):
    if not BACKFILL_ON_START:
        return

    log(f"Backfill start (limit={BACKFILL_LIMIT})")

    for s in SYMBOLS:
        for tf in TIMEFRAMES:
            try:
                candles = ex.fetch_ohlcv(s, tf, limit=BACKFILL_LIMIT)
                repo.upsert_candles(EXCHANGE, s, tf, candles)
            except Exception as e:
                log_error(f"Backfill ERROR {s} {tf}", e)

    log("Backfill complete")
