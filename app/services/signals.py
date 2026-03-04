from statistics import mean
from app.config import *
from app.utils.logging import log_error

def calc_atr_wilder(candles, n: int):
    if len(candles) < n + 1: return None
    trs = []
    for i in range(1, len(candles)):
        h, l, pc = float(candles[i]["high"]), float(candles[i]["low"]), float(candles[i - 1]["close"])
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    if len(trs) < n: return None
    atr = sum(trs[:n]) / n
    for tr in trs[n:]: atr = (atr * (n - 1) + tr) / n
    return atr

def signal_loop(repo, shutdown_event):
    need = max(ATR_WARMUP, BREAKOUT_N + 2, VOL_AVG_N + 2, ATR_N + 2)

    while not shutdown_event.is_set():
        try:
            for s in SYMBOLS:
                for tf in TIMEFRAMES:
                    candles = repo.get_recent_candles(EXCHANGE, s, tf, need)
                    if len(candles) < need: continue

                    last, prev = candles[-1], candles[-2]
                    ts, close, prev_close, volume = last["ts_ms"], float(last["close"]), float(prev["close"]), float(last["volume"])

                    highs = [float(c["high"]) for c in candles[:-1][-BREAKOUT_N:]]
                    lows  = [float(c["low"])  for c in candles[:-1][-BREAKOUT_N:]]
                    prev_high = max(highs) if highs else None
                    prev_low  = min(lows) if lows else None

                    breakout_long = prev_high is not None and close > prev_high and prev_close <= prev_high
                    breakdown_short = prev_low is not None and close < prev_low and prev_close >= prev_low

                    vols = [float(c["volume"]) for c in candles[:-1][-VOL_AVG_N:]]
                    vol_spike, vol_mult = False, None
                    if vols:
                        avg = mean(vols)
                        if avg > 0:
                            vol_mult = round(volume / avg, 2)
                            if volume > avg * VOL_SPIKE_K: vol_spike = True

                    atr14 = calc_atr_wilder(candles, ATR_N)
                    if atr14 is None or atr14 <= 0: continue

                    entry, sl_mult, rr = close, float(ATR_SL_MULT), float(RR_TP)

                    if ENABLE_COMBO_ONLY:
                        if breakout_long and vol_spike:
                            payload = {
                                "vol_mult": vol_mult, "atr14": round(atr14, 6), "entry": entry,
                                "sl": entry - (atr14 * sl_mult), "tp": entry + (atr14 * sl_mult * rr),
                                "rr": rr, "level": float(prev_high),
                            }
                            if ENABLE_TRADES:
                                if not repo.get_open_trade(EXCHANGE, s, tf):
                                    t_id = repo.open_trade(EXCHANGE, s, tf, "LONG", ts, payload)
                                    if t_id: repo.insert_signal(EXCHANGE, s, tf, ts, "OPEN_LONG", payload)
                            else:
                                repo.insert_signal(EXCHANGE, s, tf, ts, "LONG_breakout_vol", payload)

                        elif breakdown_short and vol_spike:
                            payload = {
                                "vol_mult": vol_mult, "atr14": round(atr14, 6), "entry": entry,
                                "sl": entry + (atr14 * sl_mult), "tp": entry - (atr14 * sl_mult * rr),
                                "rr": rr, "level": float(prev_low),
                            }
                            if ENABLE_TRADES:
                                if not repo.get_open_trade(EXCHANGE, s, tf):
                                    t_id = repo.open_trade(EXCHANGE, s, tf, "SHORT", ts, payload)
                                    if t_id: repo.insert_signal(EXCHANGE, s, tf, ts, "OPEN_SHORT", payload)
                            else:
                                repo.insert_signal(EXCHANGE, s, tf, ts, "SHORT_breakdown_vol", payload)

        except Exception as e:
            log_error("Signal ERROR", e)
        shutdown_event.wait(SIGNAL_INTERVAL_SEC)
