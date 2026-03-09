import time
import json
from app.config import *
from app.utils.logging import log, log_error
from app.utils.memory import get_tick

def _calc_avg_entry(e1, s1, e2, s2):
    total = s1 + s2
    return ((e1 * s1) + (e2 * s2)) / total if total > 0 else e1

def _smallest_tf(timeframes):
    tf_sec = {"1m":60,"3m":180,"5m":300,"15m":900,"30m":1800,"1h":3600,"4h":14400,"1d":86400}
    xs = [tf for tf in (timeframes or []) if tf in tf_sec]
    return min(xs, key=lambda t: tf_sec[t]) if xs else "1m"

def entry_manager_loop(repo, shutdown_event):
    log("EntryManager V2.7 (Strict Momentum Sniper) starting")
    fallback_tf = _smallest_tf(TIMEFRAMES)

    while not shutdown_event.is_set():
        try:
            now_ms = int(time.time() * 1000)

            for st in repo.list_pending_setups():
                setup_id = int(st["id"])
                if now_ms > int(st["expires_ts_ms"]):
                    repo.mark_setup_expired(setup_id)
                    continue

                ex, s, tf, side = st["exchange"], st["symbol"], st["timeframe"], st["side"]
                if tf not in TIMEFRAMES: continue
                if repo.get_open_trade(ex, s, tf): continue

                payload = st.get("payload") or {}
                if isinstance(payload, str):
                    try: payload = json.loads(payload)
                    except Exception: payload = {}

                tick = get_tick(s)
                if tick is None:
                    c = repo.get_recent_candles(ex, s, fallback_tf, 2)
                    if not c: continue
                    low, high, last_px = float(c[-1]["low"]), float(c[-1]["high"]), float(c[-1]["close"])
                    last_ts = int(c[-1]["ts_ms"])
                else:
                    low = high = last_px = float(tick)
                    last_ts = now_ms
                
                entry1 = float(st["entry1"])
                atr14 = float(st["atr14"])
                chase_limit = atr14 * ENTRY1_CHASE_ATR_PCT

                # ========================================================
                # V2.7 STRICT MOMENTUM ENTRY LOGIC
                # Eksekusi HANYA jika harga (last_px) berada di zona momentum.
                # Mode menunggu pullback/sentuhan ulang DIHAPUS TOTAL!
                # ========================================================
                hit_entry1 = False
                fill_mode = ""
                final_fill = entry1

                if side == "LONG":
                    # Instant Fill: Harga masih di sekitar area breakout
                    if entry1 <= last_px <= (entry1 + chase_limit):
                        hit_entry1 = True
                        fill_mode = "INSTANT_BREAKOUT"
                        final_fill = last_px 
                else:
                    # Instant Fill untuk skenario SHORT
                    if entry1 >= last_px >= (entry1 - chase_limit):
                        hit_entry1 = True
                        fill_mode = "INSTANT_BREAKOUT"
                        final_fill = last_px

                if hit_entry1:
                    st["avg_entry"] = float(final_fill)
                    trade_id = repo.open_trade_from_setup(st, last_ts)
                    if trade_id:
                        repo.mark_setup_triggered(setup_id)
                        repo.insert_signal(ex, s, tf, last_ts, f"FILL_{side}_ENTRY1", {
                            "trade_id": trade_id, "entry1": float(final_fill), "sl": float(st["sl"]),
                            "tp1": float(st["tp1"]), "tp2": float(st["tp2"]), "tp3": float(st["tp3"]),
                            "fill_mode": fill_mode
                        })

            # ========================================================
            # ENTRY 2 LOGIC (Tetap dipertahankan untuk DCA/Averaging)
            # ========================================================
            for t in repo.list_open_trades():
                if t.get("filled_entry2") or t.get("entry2") is None: continue
                ex, s, tf, side, t_id = t["exchange"], t["symbol"], t["timeframe"], t["side"], int(t["id"])
                if tf not in TIMEFRAMES: continue

                tick = get_tick(s)
                if tick is None:
                    c = repo.get_recent_candles(ex, s, fallback_tf, 2)
                    if not c: continue
                    low, high, last_ts = float(c[-1]["low"]), float(c[-1]["high"]), int(c[-1]["ts_ms"])
                else:
                    low = high = float(tick)
                    last_ts = now_ms

                entry1, entry2 = float(t["entry1"]), float(t["entry2"])
                if (low <= entry2 if side == "LONG" else high >= entry2):
                    avg = _calc_avg_entry(entry1, float(t.get("entry1_size") or 0), entry2, float(t.get("entry2_size") or 0))
                    if repo.mark_entry2_filled(t_id, entry2, avg):
                        repo.insert_signal(ex, s, tf, last_ts, f"FILL_{side}_ENTRY2", {"trade_id": t_id, "entry1": entry1, "entry2": entry2, "avg_entry": avg})

        except Exception as e: log_error("EntryManager ERROR", e)
        shutdown_event.wait(1)
