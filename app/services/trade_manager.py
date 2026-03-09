import time
from app.config import *
from app.utils.logging import log, log_error
from app.utils.memory import get_tick

def _smallest_tf(timeframes):
    tf_sec = {"1m":60,"3m":180,"5m":300,"15m":900,"30m":1800,"1h":3600,"4h":14400,"1d":86400}
    xs = [tf for tf in (timeframes or []) if tf in tf_sec]
    return min(xs, key=lambda t: tf_sec[t]) if xs else "1m"

def calc_pnl_pct(side: str, entry: float, exit_px: float, size_pct: float) -> float:
    if entry <= 0: return 0.0
    raw = ((exit_px - entry) / entry) if side == "LONG" else ((entry - exit_px) / entry)
    return raw * 100.0 * size_pct

def trade_manager_loop(repo, shutdown_event):
    if not ENABLE_TRADES: return
    log("TradeManager V2.8 (DB-Level Isolation) starting")
    fallback_tf = _smallest_tf(TIMEFRAMES)

    while not shutdown_event.is_set():
        try:
            now_ms = int(time.time() * 1000)
            
            # 🚨 FIX GPT: Menggunakan list_open_trades(TIMEFRAMES) yang disaring DB
            trades = repo.list_open_trades(TIMEFRAMES)

            for t in trades:
                ex, s, tf = t["exchange"], t["symbol"], t["timeframe"]
                side, trade_id = t["side"], int(t["id"])

                avg_entry = float(t.get("avg_entry") or t.get("entry") or 0)
                sl = float(t["sl"])
                tp1 = float(t.get("tp1") or 0)
                tp2 = float(t.get("tp2") or 0)
                tp3 = float(t.get("tp3") or t.get("tp") or 0)

                tp1_hit, tp2_hit = bool(t.get("tp1_hit")), bool(t.get("tp2_hit"))
                rem_size, curr_pnl = float(t.get("remaining_size_pct") or 1.0), float(t.get("realized_pnl_pct") or 0.0)

                tick = get_tick(s)
                if tick is None:
                    c = repo.get_recent_candles(ex, s, fallback_tf, 2)
                    if not c: continue
                    hi, lo, ts = float(c[-1]["high"]), float(c[-1]["low"]), int(c[-1]["ts_ms"])
                else:
                    hi = lo = float(tick)
                    ts = now_ms

                if side == "LONG":
                    if not tp1_hit and hi >= tp1:
                        pnl_added = calc_pnl_pct("LONG", avg_entry, tp1, TP1_CLOSE_PCT)
                        new_sl = avg_entry if MOVE_SL_TO_BE_AFTER_TP1 else sl
                        if repo.mark_partial_tp(trade_id, 1, TP1_CLOSE_PCT, pnl_added, new_sl):
                            repo.insert_signal(ex, s, tf, ts, "PARTIAL_TP1", {"trade_id": trade_id, "side": side, "exit": tp1, "closed_pct": TP1_CLOSE_PCT, "rem_pct": max(rem_size - TP1_CLOSE_PCT, 0.0), "pnl_added": pnl_added, "total_pnl": curr_pnl + pnl_added, "sl_moved": MOVE_SL_TO_BE_AFTER_TP1})
                        continue
                    if tp1_hit and not tp2_hit and hi >= tp2:
                        pnl_added = calc_pnl_pct("LONG", avg_entry, tp2, TP2_CLOSE_PCT)
                        new_sl = tp1 if MOVE_SL_TO_TP1_AFTER_TP2 else None
                        if repo.mark_partial_tp(trade_id, 2, TP2_CLOSE_PCT, pnl_added, new_sl):
                            repo.insert_signal(ex, s, tf, ts, "PARTIAL_TP2", {"trade_id": trade_id, "side": side, "exit": tp2, "closed_pct": TP2_CLOSE_PCT, "rem_pct": max(rem_size - TP2_CLOSE_PCT, 0.0), "pnl_added": pnl_added, "total_pnl": curr_pnl + pnl_added, "sl_moved_to_tp1": MOVE_SL_TO_TP1_AFTER_TP2})
                        continue
                    if hi >= tp3:
                        pnl_added = calc_pnl_pct("LONG", avg_entry, tp3, rem_size)
                        if repo.close_trade_v25(trade_id, ts, tp3, "TP3", pnl_added, hit_tp3=True):
                            repo.insert_signal(ex, s, tf, ts, "CLOSE_TP3", {"trade_id": trade_id, "side": side, "entry": avg_entry, "close_price": tp3, "total_pnl": curr_pnl + pnl_added, "reason": "TP3"})
                        continue
                    if lo <= sl:
                        pnl_added = calc_pnl_pct("LONG", avg_entry, sl, rem_size)
                        reason = "SL (Break-Even)" if abs(sl - avg_entry) < 1e-12 else ("SL (Trailing Profit)" if sl > avg_entry else "SL")
                        if repo.close_trade_v25(trade_id, ts, sl, reason, pnl_added, hit_tp3=False):
                            repo.insert_signal(ex, s, tf, ts, "CLOSE_SL", {"trade_id": trade_id, "side": side, "entry": avg_entry, "close_price": sl, "total_pnl": curr_pnl + pnl_added, "reason": reason})
                        continue
                else:
                    if not tp1_hit and lo <= tp1:
                        pnl_added = calc_pnl_pct("SHORT", avg_entry, tp1, TP1_CLOSE_PCT)
                        new_sl = avg_entry if MOVE_SL_TO_BE_AFTER_TP1 else sl
                        if repo.mark_partial_tp(trade_id, 1, TP1_CLOSE_PCT, pnl_added, new_sl):
                            repo.insert_signal(ex, s, tf, ts, "PARTIAL_TP1", {"trade_id": trade_id, "side": side, "exit": tp1, "closed_pct": TP1_CLOSE_PCT, "rem_pct": max(rem_size - TP1_CLOSE_PCT, 0.0), "pnl_added": pnl_added, "total_pnl": curr_pnl + pnl_added, "sl_moved": MOVE_SL_TO_BE_AFTER_TP1})
                        continue
                    if tp1_hit and not tp2_hit and lo <= tp2:
                        pnl_added = calc_pnl_pct("SHORT", avg_entry, tp2, TP2_CLOSE_PCT)
                        new_sl = tp1 if MOVE_SL_TO_TP1_AFTER_TP2 else None
                        if repo.mark_partial_tp(trade_id, 2, TP2_CLOSE_PCT, pnl_added, new_sl):
                            repo.insert_signal(ex, s, tf, ts, "PARTIAL_TP2", {"trade_id": trade_id, "side": side, "exit": tp2, "closed_pct": TP2_CLOSE_PCT, "rem_pct": max(rem_size - TP2_CLOSE_PCT, 0.0), "pnl_added": pnl_added, "total_pnl": curr_pnl + pnl_added, "sl_moved_to_tp1": MOVE_SL_TO_TP1_AFTER_TP2})
                        continue
                    if lo <= tp3:
                        pnl_added = calc_pnl_pct("SHORT", avg_entry, tp3, rem_size)
                        if repo.close_trade_v25(trade_id, ts, tp3, "TP3", pnl_added, hit_tp3=True):
                            repo.insert_signal(ex, s, tf, ts, "CLOSE_TP3", {"trade_id": trade_id, "side": side, "entry": avg_entry, "close_price": tp3, "total_pnl": curr_pnl + pnl_added, "reason": "TP3"})
                        continue
                    if hi >= sl:
                        pnl_added = calc_pnl_pct("SHORT", avg_entry, sl, rem_size)
                        reason = "SL (Break-Even)" if abs(sl - avg_entry) < 1e-12 else ("SL (Trailing Profit)" if sl < avg_entry else "SL")
                        if repo.close_trade_v25(trade_id, ts, sl, reason, pnl_added, hit_tp3=False):
                            repo.insert_signal(ex, s, tf, ts, "CLOSE_SL", {"trade_id": trade_id, "side": side, "entry": avg_entry, "close_price": sl, "total_pnl": curr_pnl + pnl_added, "reason": reason})
                        continue

        except Exception as e:
            log_error("TradeManager V2.8 ERROR", e)
        shutdown_event.wait(1 if ENABLE_WS_TICKER else TRADE_MANAGER_INTERVAL_SEC)
