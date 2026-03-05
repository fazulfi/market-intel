import time
from app.config import *
from app.utils.logging import log, log_error
from app.utils.memory import get_tick

def trade_manager_loop(repo, shutdown_event):
    if not ENABLE_TRADES:
        return

    log("TradeManager V1.9 (WS-first, REST fallback) starting")

    while not shutdown_event.is_set():
        try:
            trades = repo.list_open_trades()
            if not trades:
                shutdown_event.wait(TRADE_MANAGER_INTERVAL_SEC)
                continue

            for t in trades:
                ex, s, tf = t["exchange"], t["symbol"], t["timeframe"]
                side, trade_id = t["side"], int(t["id"])
                tp, sl = float(t["tp"]), float(t["sl"])

                reason = None
                close_price = None
                ts = None

                # 1) FAST: WS tick
                tick_px = get_tick(s)
                if tick_px is not None:
                    if side == "LONG":
                        if tick_px >= tp:
                            reason, close_price = "TP", tick_px
                        elif tick_px <= sl:
                            reason, close_price = "SL", tick_px
                    else:
                        if tick_px <= tp:
                            reason, close_price = "TP", tick_px
                        elif tick_px >= sl:
                            reason, close_price = "SL", tick_px
                    ts = int(time.time() * 1000)

                # 2) FALLBACK: candle hi/lo (kalau WS putus / belum dapet tick)
                if reason is None:
                    candles = repo.get_recent_candles(ex, s, tf, 2)
                    if not candles:
                        continue
                    last = candles[-1]
                    hi, lo = float(last["high"]), float(last["low"])
                    ts = int(last["ts_ms"])

                    if side == "LONG":
                        if hi >= tp and lo <= sl:
                            reason, close_price = ("TP", tp) if CLOSE_RULE == "optimistic" else ("SL", sl)
                        elif hi >= tp:
                            reason, close_price = "TP", tp
                        elif lo <= sl:
                            reason, close_price = "SL", sl
                    else:
                        if lo <= tp and hi >= sl:
                            reason, close_price = ("TP", tp) if CLOSE_RULE == "optimistic" else ("SL", sl)
                        elif lo <= tp:
                            reason, close_price = "TP", tp
                        elif hi >= sl:
                            reason, close_price = "SL", sl

                if reason and close_price is not None and ts is not None:
                    if repo.close_trade(trade_id, ts, float(close_price), reason):
                        payload = {
                            "trade_id": trade_id,
                            "side": side,
                            "entry": float(t["entry"]),
                            "close_price": float(close_price),
                            "close_reason": reason,
                            "ws_tick": bool(tick_px is not None),
                        }
                        stype = "CLOSE_TP" if reason == "TP" else "CLOSE_SL"
                        repo.insert_signal(ex, s, tf, ts, stype, payload)
                        log(f"Closed trade {trade_id} {s} {tf} {stype} @ {float(close_price):.6f} ws={payload['ws_tick']}")

        except Exception as e:
            log_error("TradeManager ERROR", e)

        shutdown_event.wait(1 if ENABLE_WS_TICKER else TRADE_MANAGER_INTERVAL_SEC)
