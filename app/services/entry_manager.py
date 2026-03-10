import time
import json
from app.config import EMERGENCY_STOP, TIMEFRAMES, ENTRY1_CHASE_ATR_PCT
from app.utils.logging import log, log_error
from app.utils.memory import get_tick
from app.utils.timeframes import smallest_tf
from app.execution.bybit_executor import BybitExecutor

def _calc_avg_entry(e1, s1, e2, s2):
    total = s1 + s2
    return ((e1 * s1) + (e2 * s2)) / total if total > 0 else e1


def entry_manager_loop(repo, shutdown_event):
    log("EntryManager V2.8 (DB-Level Isolation) starting")
    fallback_tf = smallest_tf(TIMEFRAMES)
    executor = BybitExecutor()

    while not shutdown_event.is_set():
        if EMERGENCY_STOP:
            log("🚨 EMERGENCY STOP ACTIVE: Entry Manager is HALTED! No new entries will be executed.")
            shutdown_event.wait(10)
            continue
            
        try:
            now_ms = int(time.time() * 1000)

            # 🚨 FIX GPT: Minta PENDING SETUP yang HANYA milik Timeframe ini (Level DB)
            for st in repo.list_pending_setups(TIMEFRAMES):
                setup_id = int(st["id"])
                
                # Expiry check sekarang 1000% aman karena data ini PASTI milik bot ini
                if now_ms > int(st["expires_ts_ms"]):
                    repo.mark_setup_expired(setup_id)
                    continue

                ex, s, tf, side = st["exchange"], st["symbol"], st["timeframe"], st["side"]
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

                hit_entry1 = False
                fill_mode = ""
                final_fill = entry1

                if side == "LONG":
                    if entry1 <= last_px <= (entry1 + chase_limit):
                        hit_entry1 = True
                        fill_mode = "INSTANT_BREAKOUT"
                        final_fill = last_px 
                else:
                    if entry1 >= last_px >= (entry1 - chase_limit):
                        hit_entry1 = True
                        fill_mode = "INSTANT_BREAKOUT"
                        final_fill = last_px

                if hit_entry1:
                    # 🚀 WIRING V4.0: Hitung Qty & Tembak Order!
                    qty_total = executor.calc_order_qty(s, final_fill, risk_pct=0.02) # 2% Saldo
                    qty1 = executor.format_qty(s, qty_total * float(st.get("entry1_size", 0.3))) # Ambil 30% nya
                    
                    order_type = "market" if fill_mode == "INSTANT_BREAKOUT" else "limit"
                    executor.place_order(s, side, order_type, qty1, final_fill)

                    st["avg_entry"] = float(final_fill)
                    trade_id = repo.open_trade_from_setup(st, last_ts)
                    if trade_id:
                        repo.mark_setup_triggered(setup_id)
                        repo.insert_signal(ex, s, tf, last_ts, f"FILL_{side}_ENTRY1", {
                            "trade_id": trade_id, "entry1": float(final_fill), "sl": float(st["sl"]),
                            "tp1": float(st["tp1"]), "tp2": float(st["tp2"]), "tp3": float(st["tp3"]),
                            "fill_mode": fill_mode
                        })

            # 🚨 FIX GPT: Minta OPEN TRADES yang HANYA milik Timeframe ini (Level DB)
            for t in repo.list_open_trades(TIMEFRAMES):
                if t.get("filled_entry2") or t.get("entry2") is None: continue
                ex, s, tf, side, t_id = t["exchange"], t["symbol"], t["timeframe"], t["side"], int(t["id"])

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
                    # 🚀 WIRING V4.0: Tembak Order Limit untuk Entry 2
                    qty_total = executor.calc_order_qty(s, entry2, risk_pct=0.02)
                    qty2 = executor.format_qty(s, qty_total * float(t.get("entry2_size", 0.7))) # Ambil 70% nya
                    executor.place_order(s, side, "limit", qty2, entry2)

                    avg = _calc_avg_entry(entry1, float(t.get("entry1_size") or 0), entry2, float(t.get("entry2_size") or 0))
                    if repo.mark_entry2_filled(t_id, avg):
                        repo.insert_signal(ex, s, tf, last_ts, f"FILL_{side}_ENTRY2", {"trade_id": t_id, "entry1": entry1, "entry2": entry2, "avg_entry": avg})

        except Exception as e: log_error("EntryManager ERROR", e)
        shutdown_event.wait(1)
