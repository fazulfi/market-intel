import time
from app.config import *
from app.utils.logging import log, log_error
from app.utils.memory import get_tick

def _smallest_tf(timeframes):
    tf_sec = {"1m":60,"3m":180,"5m":300,"15m":900,"30m":1800,"1h":3600,"4h":14400,"1d":86400}
    xs = [tf for tf in (timeframes or []) if tf in tf_sec]
    return min(xs, key=lambda t: tf_sec[t]) if xs else "1m"

def trade_manager_loop(repo, shutdown_event):
    if not ENABLE_TRADES: return
    log("TradeManager V2.4 starting")
    fallback_tf = _smallest_tf(TIMEFRAMES)

    while not shutdown_event.is_set():
        try:
            trades = repo.list_open_trades()
            for t in trades:
                ex, s, tf, side, trade_id = t["exchange"], t["symbol"], t["timeframe"], t["side"], int(t["id"])
                tp, sl = float(t["tp"]), float(t["sl"]) # Eksekusi Close All di TP3
                reason, close_price, ts = None, None, None

                tick = get_tick(s)
                if tick is not None:
                    if side == "LONG":
                        if tick >= tp: reason, close_price = "TP", tick
                        elif tick <= sl: reason, close_price = "SL", tick
                    else:
                        if tick <= tp: reason, close_price = "TP", tick
                        elif tick >= sl: reason, close_price = "SL", tick
                    ts = int(time.time() * 1000)
                
                if reason is None:
                    c = repo.get_recent_candles(ex, s, fallback_tf, 2)
                    if not c: continue
                    hi, lo, ts = float(c[-1]["high"]), float(c[-1]["low"]), int(c[-1]["ts_ms"])
                    if side == "LONG":
                        if hi >= tp and lo <= sl: reason, close_price = ("TP", tp) if CLOSE_RULE == "optimistic" else ("SL", sl)
                        elif hi >= tp: reason, close_price = "TP", tp
                        elif lo <= sl: reason, close_price = "SL", sl
                    else:
                        if lo <= tp and hi >= sl: reason, close_price = ("TP", tp) if CLOSE_RULE == "optimistic" else ("SL", sl)
                        elif lo <= tp: reason, close_price = "TP", tp
                        elif hi >= sl: reason, close_price = "SL", sl

                if reason and close_price is not None and ts is not None:
                    if repo.close_trade(trade_id, ts, float(close_price), reason):
                        stype = "CLOSE_TP" if reason == "TP" else "CLOSE_SL"
                        payload = {"trade_id": trade_id, "side": side, "entry": float(t.get("avg_entry") or t.get("entry")), "close_price": float(close_price), "close_reason": reason, "ws_tick": bool(tick is not None)}
                        repo.insert_signal(ex, s, tf, ts, stype, payload)
                        log(f"Closed trade {trade_id} {s} {tf} {stype} @ {close_price}")

        except Exception as e: log_error("TradeManager ERROR", e)
        shutdown_event.wait(1 if ENABLE_WS_TICKER else TRADE_MANAGER_INTERVAL_SEC)
