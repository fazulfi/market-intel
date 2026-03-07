from app.config import *
from app.utils.logging import log, log_error

def run_backfill(repo, ex):
    if not BACKFILL_ON_START:
        return

    # Kumpulkan SEMUA Timeframe secara absolut (Utama + Trend + ATR)
    all_tfs = set(TIMEFRAMES)
    for tf in TREND_TF_MAP.values():
        all_tfs.add(tf)
    for tf in ATR_TF_MAP.values():
        all_tfs.add(tf)

    log(f"Backfill start for {len(SYMBOLS)} tickers & {len(all_tfs)} TFs (limit={BACKFILL_LIMIT})...")

    total_candles = 0
    for s in SYMBOLS:
        for tf in all_tfs:
            try:
                candles = ex.fetch_ohlcv(s, tf, limit=BACKFILL_LIMIT)
                if candles:
                    repo.upsert_candles(EXCHANGE, s, tf, candles)
                    total_candles += len(candles)
            except Exception as e:
                log_error(f"Backfill ERROR {s} {tf}", e)

    log(f"Backfill complete! Menelan {total_candles} candles dari {len(SYMBOLS)} ticker. Mesin siap tempur!")
