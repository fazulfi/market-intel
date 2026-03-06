import time
from app.config import *
from app.utils.logging import log, log_error
from app.utils.memory import get_tick

def _calc_avg_entry(entry1, size1, entry2, size2):
    total = size1 + size2
    return ((entry1 * size1) + (entry2 * size2)) / total if total > 0 else entry1

def _smallest_tf(timeframes):
    tf_sec = {"1m":60,"3m":180,"5m":300,"15m":900,"30m":1800,"1h":3600,"4h":14400,"1d":86400}
    xs = [tf for tf in (timeframes or []) if tf in tf_sec]
    return min(xs, key=lambda t: tf_sec[t]) if xs else "1m"

def entry_manager_loop(repo, shutdown_event):
    log("EntryManager V2.3 starting")
    fallback_tf = _smallest_tf(TIMEFRAMES)

    while not shutdown_event.is_set():
        try:
            trades = repo.list_open_trades()
            if not trades:
                shutdown_event.wait(1)
                continue

            for t in trades:
                if t.get("filled_entry2") or t.get("entry2") is None:
                    continue

                ex, s, tf = t["exchange"], t["symbol"], t["timeframe"]
                side, trade_id = t["side"], int(t["id"])
                entry1 = float(t["entry1"])
                entry2 = float(t["entry2"])
                size1 = float(t.get("entry1_size") or 0)
                size2 = float(t.get("entry2_size") or 0)

                tick_px = get_tick(s)
                if tick_px is None:
                    candles = repo.get_recent_candles(ex, s, fallback_tf, 2)
                    if not candles:
                        continue
                    low = float(candles[-1]["low"])
                    high = float(candles[-1]["high"])
                    touched = low <= entry2 if side == "LONG" else high >= entry2
                else:
                    touched = float(tick_px) <= entry2 if side == "LONG" else float(tick_px) >= entry2

                if not touched:
                    continue

                avg_entry = _calc_avg_entry(entry1, size1, entry2, size2)
                if repo.mark_entry2_filled(trade_id, entry2, avg_entry):
                    repo.insert_signal(ex, s, tf, int(time.time() * 1000), f"OPEN_{side}_STEP2", {
                        "trade_id": trade_id,
                        "entry1": entry1,
                        "entry2": entry2,
                        "avg_entry": avg_entry,
                    })

        except Exception as e:
            log_error("EntryManager ERROR", e)

        shutdown_event.wait(1)
