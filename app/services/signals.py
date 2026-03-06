from statistics import mean
from app.config import *
from app.utils.logging import log_error

def ema(values, n: int):
    if len(values) < n:
        return None
    k = 2.0 / (n + 1.0)
    e = float(values[0])
    for v in values[1:]:
        e = (float(v) - e) * k + e
    return e

def calc_atr_wilder(candles, n: int):
    if len(candles) < n + 1:
        return None
    trs = [
        max(
            float(candles[i]["high"]) - float(candles[i]["low"]),
            abs(float(candles[i]["high"]) - float(candles[i - 1]["close"])),
            abs(float(candles[i]["low"]) - float(candles[i - 1]["close"]))
        )
        for i in range(1, len(candles))
    ]
    if len(trs) < n:
        return None
    atr = sum(trs[:n]) / n
    for tr in trs[n:]:
        atr = (atr * (n - 1) + tr) / n
    return atr

def signal_loop(repo, shutdown_event):
    need = max(ATR_WARMUP, BREAKOUT_N + 2, VOL_AVG_N + 2, ATR_N + 2)

    while not shutdown_event.is_set():
        try:
            for s in SYMBOLS:
                for tf in TIMEFRAMES:
                    trend_tf = TREND_TF_MAP.get(tf, EMA_TREND_TF)
                    atr_tf = ATR_TF_MAP.get(tf, tf)

                    # preserve large warmup
                    trend_need = max(EMA_TREND_N * 2, 400)
                    trend_candles = repo.get_recent_candles(EXCHANGE, s, trend_tf, trend_need)
                    if len(trend_candles) < EMA_TREND_N + 5:
                        continue

                    trend_closes = [c["close"] for c in trend_candles]
                    ema_now = ema(trend_closes, EMA_TREND_N)
                    ema_prev = ema(trend_closes[:-5], EMA_TREND_N)
                    if ema_now is None or ema_prev is None:
                        continue

                    curr_close = float(trend_closes[-1])
                    trend_up = curr_close > ema_now and ema_now > ema_prev
                    trend_down = curr_close < ema_now and ema_now < ema_prev

                    # main breakout candles
                    candles = repo.get_recent_candles(EXCHANGE, s, tf, need)
                    if len(candles) < need:
                        continue

                    last, prev = candles[-1], candles[-2]
                    ts = int(last["ts_ms"])
                    close = float(last["close"])
                    prev_close = float(prev["close"])
                    vol = float(last["volume"])

                    highs = [float(c["high"]) for c in candles[:-1][-BREAKOUT_N:]]
                    lows = [float(c["low"]) for c in candles[:-1][-BREAKOUT_N:]]
                    if not highs or not lows:
                        continue

                    level_hi = max(highs)
                    level_lo = min(lows)

                    breakout_long = close > level_hi and prev_close <= level_hi
                    breakdown_short = close < level_lo and prev_close >= level_lo

                    vols = [float(c["volume"]) for c in candles[:-1][-VOL_AVG_N:]]
                    if not vols:
                        continue
                    avg = mean(vols)
                    if avg <= 0:
                        continue

                    vol_mult = round(vol / avg, 2)
                    vol_spike = vol > avg * VOL_SPIKE_K

                    atr_need = max(ATR_WARMUP, ATR_N + 20)
                    atr_candles = repo.get_recent_candles(EXCHANGE, s, atr_tf, atr_need)
                    if len(atr_candles) < ATR_N + 2:
                        continue

                    atr14 = calc_atr_wilder(atr_candles, ATR_N)
                    if atr14 is None or atr14 <= 0:
                        continue

                    # enforce one open trade
                    if repo.get_open_trade(EXCHANGE, s, tf):
                        continue

                    # cooldown ONLY after close
                    if repo.has_recent_closed_trade(EXCHANGE, s, tf, POST_CLOSE_COOLDOWN_SEC):
                        continue

                    if breakout_long and vol_spike and trend_up:
                        entry1 = float(level_hi)
                        entry2 = float(level_hi - atr14 * ENTRY2_ATR_MULT) if ENABLE_ENTRY2 else None
                        sl = float(entry2 - atr14 * ATR_SL_MULT) if entry2 is not None else float(entry1 - atr14 * ATR_SL_MULT)
                        tp = float(entry1 + (entry1 - sl) * RR_TP)

                        payload = {
                            "entry": entry1,
                            "entry1": entry1,
                            "entry2": entry2,
                            "entry1_size": ENTRY1_SIZE,
                            "entry2_size": ENTRY2_SIZE,
                            "filled_entry2": False,
                            "avg_entry": entry1,
                            "sl": sl,
                            "tp": tp,
                            "atr14": round(atr14, 6),
                            "vol_mult": vol_mult,
                            "level": float(level_hi),
                            "trend_tf": trend_tf,
                            "atr_tf": atr_tf,
                        }

                        trade_id = repo.open_trade_two_step(EXCHANGE, s, tf, "LONG", ts, payload)
                        if trade_id:
                            repo.insert_signal(EXCHANGE, s, tf, ts, "OPEN_LONG_STEP1", {"trade_id": trade_id, **payload})

                    elif breakdown_short and vol_spike and trend_down:
                        entry1 = float(level_lo)
                        entry2 = float(level_lo + atr14 * ENTRY2_ATR_MULT) if ENABLE_ENTRY2 else None
                        sl = float(entry2 + atr14 * ATR_SL_MULT) if entry2 is not None else float(entry1 + atr14 * ATR_SL_MULT)
                        tp = float(entry1 - (sl - entry1) * RR_TP)

                        payload = {
                            "entry": entry1,
                            "entry1": entry1,
                            "entry2": entry2,
                            "entry1_size": ENTRY1_SIZE,
                            "entry2_size": ENTRY2_SIZE,
                            "filled_entry2": False,
                            "avg_entry": entry1,
                            "sl": sl,
                            "tp": tp,
                            "atr14": round(atr14, 6),
                            "vol_mult": vol_mult,
                            "level": float(level_lo),
                            "trend_tf": trend_tf,
                            "atr_tf": atr_tf,
                        }

                        trade_id = repo.open_trade_two_step(EXCHANGE, s, tf, "SHORT", ts, payload)
                        if trade_id:
                            repo.insert_signal(EXCHANGE, s, tf, ts, "OPEN_SHORT_STEP1", {"trade_id": trade_id, **payload})

        except Exception as e:
            log_error("Signal ERROR", e)

        shutdown_event.wait(SIGNAL_INTERVAL_SEC)
