from app.config import *
from app.utils.logging import log, log_error

def run_backfill(repo, ex):
    if not BACKFILL_ON_START:
        return

    # Kumpulkan SEMUA Timeframe secara absolut (Utama + Trend + ATR)
    all_tfs = set(TIMEFRAMES)
    
    # Tambahkan semua TF yang dibutuhkan oleh Trend EMA
    for tf in TREND_TF_MAP.values():
        all_tfs.add(tf)
        
    # Tambahkan semua TF yang dibutuhkan oleh ATR
    for tf in ATR_TF_MAP.values():
        all_tfs.add(tf)

    log(f"Backfill start (limit={BACKFILL_LIMIT}) for TFs: {', '.join(all_tfs)}")

    for s in SYMBOLS:
        for tf in all_tfs:
            try:
                candles = ex.fetch_ohlcv(s, tf, limit=BACKFILL_LIMIT)
                if candles:
                    repo.upsert_candles(EXCHANGE, s, tf, candles)
                    log(f"Backfilled {s} {tf}: {len(candles)} candles")
            except Exception as e:
                log_error(f"Backfill ERROR {s} {tf}", e)

    log("Backfill complete! Semua TF sudah terisi.")
