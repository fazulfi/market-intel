from app.config import *
from app.utils.logging import log, log_error

def _decide_close(side: str, last, tp: float, sl: float, rule: str):
    hi, lo = float(last["high"]), float(last["low"])
    if side == "LONG":
        if hi >= tp and lo <= sl: return ("TP", tp) if rule == "optimistic" else ("SL", sl)
        if hi >= tp: return "TP", tp
        if lo <= sl: return "SL", sl
    else:
        if lo <= tp and hi >= sl: return ("TP", tp) if rule == "optimistic" else ("SL", sl)
        if lo <= tp: return "TP", tp
        if hi >= sl: return "SL", sl
    return None, None

def trade_manager_loop(repo, shutdown_event):
    if not ENABLE_TRADES: return
    log("TradeManager V1.6 starting")

    while not shutdown_event.is_set():
        try:
            trades = repo.list_open_trades()
            if not trades:
                shutdown_event.wait(TRADE_MANAGER_INTERVAL_SEC)
                continue

            for t in trades:
                ex, s, tf, side, trade_id = t["exchange"], t["symbol"], t["timeframe"], t["side"], int(t["id"])
                
                candles = repo.get_recent_candles(ex, s, tf, 2)
                if not candles: continue
                last = candles[-1]
                ts = int(last["ts_ms"])

                reason, close_price = _decide_close(side, last, float(t["tp"]), float(t["sl"]), CLOSE_RULE)
                if not reason: continue

                if repo.close_trade(trade_id, ts, close_price, reason):
                    payload = {
                        "trade_id": trade_id, "side": side, "entry": float(t["entry"]),
                        "close_price": float(close_price), "close_reason": reason,
                        "vol_mult": t.get("vol_mult"), "atr14": t.get("atr14"),
                    }
                    stype = "CLOSE_TP" if reason == "TP" else "CLOSE_SL"
                    repo.insert_signal(ex, s, tf, ts, stype, payload)
                    log(f"Closed trade {trade_id} {s} {tf} {stype}")

        except Exception as e:
            log_error("TradeManager ERROR", e)
        shutdown_event.wait(TRADE_MANAGER_INTERVAL_SEC)
