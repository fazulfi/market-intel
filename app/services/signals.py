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

_TF_SEC = {"1m":60, "3m":180, "5m":300, "15m":900, "30m":1800, "1h":3600}
def tf_to_ms(tf: str) -> int:
    return _TF_SEC.get(tf, 60) * 1000

def signal_loop(repo, shutdown_event):
    need = max(ATR_WARMUP, BREAKOUT_N + 2, VOL_AVG_N + 2, ATR_N + 2)

    while not shutdown_event.is_set():
        try:
            for s in SYMBOLS:
                # trend candles ambil sekali per symbol agar hemat DB
                trend_need = max(EMA_TREND_N + 5, 220)
                trend_candles = repo.get_recent_candles(EXCHANGE, s, EMA_TREND_TF, trend_need)
                if len(trend_candles) < EMA_TREND_N:
                    continue

                trend_closes = [c["close"] for c in trend_candles]
                ema200 = ema(trend_closes[-EMA_TREND_N:], EMA_TREND_N)
                if ema200 is None:
                    continue

                trend_up = float(trend_closes[-1]) > float(ema200)
                trend_down = float(trend_closes[-1]) < float(ema200)

                for tf in TIMEFRAMES:
                    candles = repo.get_recent_candles(EXCHANGE, s, tf, need)
                    if len(candles) < need:
                        continue

                    last = candles[-1]
                    prev = candles[-2]
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

                    atr14 = calc_atr_wilder(candles, ATR_N)
                    if atr14 is None or atr14 <= 0:
                        continue

                    if not ENABLE_COMBO_ONLY:
                        continue

                    # only create setup when breakout/breakdown + vol spike + trend filter
                    if breakout_long and vol_spike and trend_up:
                        expires_ts = ts + tf_to_ms(tf) * RETEST_MAX_BARS
                        payload = {
                            "vol_mult": vol_mult,
                            "atr14": round(atr14, 6),
                            "ema200": float(ema200),
                            "trend_tf": EMA_TREND_TF,
                            "entry_ref": close,
                            "level": float(level_hi),
                        }
                        repo.upsert_setup_pending(EXCHANGE, s, tf, "LONG", ts, expires_ts, float(level_hi), payload)
                        repo.insert_signal(EXCHANGE, s, tf, ts, "SETUP_LONG_retest", payload)

                    elif breakdown_short and vol_spike and trend_down:
                        expires_ts = ts + tf_to_ms(tf) * RETEST_MAX_BARS
                        payload = {
                            "vol_mult": vol_mult,
                            "atr14": round(atr14, 6),
                            "ema200": float(ema200),
                            "trend_tf": EMA_TREND_TF,
                            "entry_ref": close,
                            "level": float(level_lo),
                        }
                        repo.upsert_setup_pending(EXCHANGE, s, tf, "SHORT", ts, expires_ts, float(level_lo), payload)
                        repo.insert_signal(EXCHANGE, s, tf, ts, "SETUP_SHORT_retest", payload)

        except Exception as e:
            log_error("Signal ERROR", e)

        shutdown_event.wait(SIGNAL_INTERVAL_SEC)
