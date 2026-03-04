from statistics import mean
from app.config import *
from app.utils.logging import log_error


def signal_loop(repo, shutdown_event):
    need = max(BREAKOUT_N, VOL_AVG_N) + 2

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
                    open_ = last["open"]
                    close = last["close"]
                    volume = last["volume"]

                    direction = "LONG" if close > open_ else "SHORT"

                    # ===== BREAKOUT / BREAKDOWN =====
                    highs = [c["high"] for c in candles[:-1][-BREAKOUT_N:]]
                    lows  = [c["low"]  for c in candles[:-1][-BREAKOUT_N:]]

                    breakout_long = False
                    breakdown_short = False

                    if highs:
                        level_hi = max(highs)
                        if close > level_hi and prev["close"] <= level_hi:
                            breakout_long = True

                    if lows:
                        level_lo = min(lows)
                        if close < level_lo and prev["close"] >= level_lo:
                            breakdown_short = True

                    # ===== VOLUME SPIKE + MULT =====
                    vols = [c["volume"] for c in candles[:-1][-VOL_AVG_N:]]
                    vol_spike = False
                    vol_mult = None

                    if vols:
                        avg = mean(vols)
                        if avg > 0 and volume > avg * VOL_SPIKE_K:
                            vol_spike = True
                            vol_mult = round(volume / avg, 2)

                    # ===== COMBO =====
                    if ENABLE_COMBO_SIGNAL and breakout_long and vol_spike:
                        repo.insert_signal(EXCHANGE, s, tf, ts, "LONG_breakout_vol", {"vol_mult": vol_mult})

                    elif ENABLE_COMBO_SIGNAL and breakdown_short and vol_spike:
                        repo.insert_signal(EXCHANGE, s, tf, ts, "SHORT_breakdown_vol", {"vol_mult": vol_mult})

                    else:
                        if breakout_long:
                            repo.insert_signal(EXCHANGE, s, tf, ts, "LONG_breakout", {})

                        if breakdown_short:
                            repo.insert_signal(EXCHANGE, s, tf, ts, "SHORT_breakdown", {})

                        if vol_spike:
                            repo.insert_signal(EXCHANGE, s, tf, ts, f"{direction}_vol_spike", {"vol_mult": vol_mult})

        except Exception as e:
            log_error("Signal ERROR", e)

        shutdown_event.wait(SIGNAL_INTERVAL_SEC)
