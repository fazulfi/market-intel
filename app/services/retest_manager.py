import json
import time
from app.config import *
from app.utils.logging import log, log_error

def _touch_long(last, level):
    level = float(level)
    if RETEST_TOUCH_MODE == "close":
        return float(last["close"]) <= level
    return float(last["low"]) <= level

def _touch_short(last, level):
    level = float(level)
    if RETEST_TOUCH_MODE == "close":
        return float(last["close"]) >= level
    return float(last["high"]) >= level

def retest_manager_loop(repo, shutdown_event):
    log("RetestManager V1.8 starting")

    while not shutdown_event.is_set():
        try:
            setups = repo.list_pending_setups()
            now_ms = int(time.time() * 1000)

            for st in setups:
                setup_id = int(st["id"])
                ex = st["exchange"]
                s = st["symbol"]
                tf = st["timeframe"]
                side = st["side"]
                level = float(st["level"])
                expires_ts = int(st["expires_ts_ms"])

                if now_ms > expires_ts:
                    repo.mark_setup_expired(setup_id)
                    continue

                # enforce: 1 open trade per pair
                if repo.get_open_trade(ex, s, tf):
                    continue

                candles = repo.get_recent_candles(ex, s, tf, 3)
                if len(candles) < 2:
                    continue

                last = candles[-1]
                payload = st.get("payload") or {}
                if isinstance(payload, str):
                    try: payload = json.loads(payload)
                    except: payload = {}

                # retest condition: touch level + close back to direction
                if side == "LONG":
                    triggered = _touch_long(last, level) and float(last["close"]) > level
                else:
                    triggered = _touch_short(last, level) and float(last["close"]) < level

                if not triggered:
                    continue

                entry = float(last["close"])
                atr14 = float(payload.get("atr14") or 0.0)
                if atr14 <= 0:
                    continue

                sl_mult = float(ATR_SL_MULT)
                rr = float(RR_TP)

                if side == "LONG":
                    sl = entry - atr14 * sl_mult
                    tp = entry + atr14 * sl_mult * rr
                else:
                    sl = entry + atr14 * sl_mult
                    tp = entry - atr14 * sl_mult * rr

                trade_payload = dict(payload)
                trade_payload.update({"entry": entry, "sl": sl, "tp": tp, "retest_level": level})

                trade_id = repo.open_trade(ex, s, tf, side, int(last["ts_ms"]), trade_payload)
                if trade_id:
                    repo.mark_setup_triggered(setup_id)
                    repo.insert_signal(ex, s, tf, int(last["ts_ms"]), f"OPEN_{side}_retest", {"trade_id": trade_id, **trade_payload})

        except Exception as e:
            log_error("RetestManager ERROR", e)

        shutdown_event.wait(1)
