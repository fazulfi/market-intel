from statistics import mean
from app.config import *
from app.utils.logging import log_error

def calc_atr_wilder(candles, n: int):
    if len(candles) < n + 1:
        return None

    trs = []
    for i in range(1, len(candles)):
        h = float(candles[i]["high"])
        l = float(candles[i]["low"])
        pc = float(candles[i - 1]["close"])
        tr = max(h - l, abs(h - pc), abs(l - pc))
        trs.append(tr)

    if len(trs) < n:
        return None

    atr = sum(trs[:n]) / n
    for tr in trs[n:]:
        atr = (atr * (n - 1) + tr) / n
    return atr

def signal_loop(repo, shutdown_event):
    # Wilder ATR perlu warmup panjang biar stabil
    need = max(ATR_WARMUP, BREAKOUT_N + 2, VOL_AVG_N + 2, ATR_N + 2)

    while not shutdown_event.is_set():
        try:
            for s in SYMBOLS:
                for tf in TIMEFRAMES:
                    candles = repo.get_recent_candles(EXCHANGE, s, tf, need)
                    if len(candles) < need:
                        continue

                    last = candles[-1]
                    prev = candles[-2]

                    ts = last["ts_ms"]
                    close = float(last["close"])
                    prev_close = float(prev["close"])
                    volume = float(last["volume"])

                    # ===== breakout / breakdown =====
                    highs = [float(c["high"]) for c in candles[:-1][-BREAKOUT_N:]]
                    lows  = [float(c["low"])  for c in candles[:-1][-BREAKOUT_N:]]

                    prev_high = max(highs) if highs else None
                    prev_low  = min(lows) if lows else None

                    breakout_long = (
                        prev_high is not None and
                        close > prev_high and
                        prev_close <= prev_high
                    )
                    breakdown_short = (
                        prev_low is not None and
                        close < prev_low and
                        prev_close >= prev_low
                    )

                    # ===== volume spike =====
                    vols = [float(c["volume"]) for c in candles[:-1][-VOL_AVG_N:]]
                    vol_spike = False
                    vol_mult = None

                    if vols:
                        avg = mean(vols)
                        if avg > 0:
                            vol_mult = round(volume / avg, 2)
                            if volume > avg * VOL_SPIKE_K:
                                vol_spike = True

                    # ===== ATR + TP/SL =====
                    atr14 = calc_atr_wilder(candles, ATR_N)  # include last candle, consistent with entry
                    if atr14 is None or atr14 <= 0:
                        continue

                    entry = close
                    sl_mult = float(ATR_SL_MULT)
                    rr = float(RR_TP)

                    if ENABLE_COMBO_ONLY:
                        if breakout_long and vol_spike:
                            sl = entry - (atr14 * sl_mult)
                            tp = entry + (atr14 * sl_mult * rr)

                            repo.insert_signal(EXCHANGE, s, tf, ts, "LONG_breakout_vol", {
                                "vol_mult": vol_mult,
                                "atr14": round(atr14, 6),
                                "entry": entry,
                                "sl": sl,
                                "tp": tp,
                                "rr": rr,
                                "level": float(prev_high),
                            })

                        elif breakdown_short and vol_spike:
                            sl = entry + (atr14 * sl_mult)
                            tp = entry - (atr14 * sl_mult * rr)

                            repo.insert_signal(EXCHANGE, s, tf, ts, "SHORT_breakdown_vol", {
                                "vol_mult": vol_mult,
                                "atr14": round(atr14, 6),
                                "entry": entry,
                                "sl": sl,
                                "tp": tp,
                                "rr": rr,
                                "level": float(prev_low),
                            })
                    else:
                        # fallback mode (kalau suatu saat mau hidupkan sinyal mentah lagi)
                        if breakout_long:
                            repo.insert_signal(EXCHANGE, s, tf, ts, "LONG_breakout", {})
                        if breakdown_short:
                            repo.insert_signal(EXCHANGE, s, tf, ts, "SHORT_breakdown", {})
                        if vol_spike:
                            direction = "LONG" if float(last["close"]) >= float(last["open"]) else "SHORT"
                            repo.insert_signal(EXCHANGE, s, tf, ts, f"{direction}_vol_spike", {"vol_mult": vol_mult})

        except Exception as e:
            log_error("Signal ERROR", e)

        shutdown_event.wait(SIGNAL_INTERVAL_SEC)
