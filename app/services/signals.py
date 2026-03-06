from statistics import mean
from app.config import *
from app.utils.logging import log_error

def ema(values, n: int):
    if len(values) < n: return None
    k = 2.0 / (n + 1.0)
    e = float(values[0])
    for v in values[1:]: e = (float(v) - e) * k + e
    return e

def calc_atr_wilder(candles, n: int):
    if len(candles) < n + 1: return None
    trs = [max(float(candles[i]["high"]) - float(candles[i]["low"]), abs(float(candles[i]["high"]) - float(candles[i - 1]["close"])), abs(float(candles[i]["low"]) - float(candles[i - 1]["close"]))) for i in range(1, len(candles))]
    if len(trs) < n: return None
    atr = sum(trs[:n]) / n
    for tr in trs[n:]: atr = (atr * (n - 1) + tr) / n
    return atr

_TF_SEC = {"1m":60, "3m":180, "5m":300, "15m":900, "30m":1800, "1h":3600, "4h":14400, "1d":86400}
def tf_to_ms(tf: str) -> int: return _TF_SEC.get(tf, 60) * 1000

def signal_loop(repo, shutdown_event):
    base_need = max(BREAKOUT_N + 2, VOL_AVG_N + 2)
    atr_need = max(ATR_WARMUP, ATR_N + 2)

    while not shutdown_event.is_set():
        try:
            for s in SYMBOLS:
                for tf in TIMEFRAMES:
                    # 1) MTF TREND + EMA SLOPE (Akurasi Tinggi)
                    trend_tf = TREND_TF_MAP.get(tf, EMA_TREND_TF)
                    trend_need = max(EMA_TREND_N * 2, 400)
                    trend_candles = repo.get_recent_candles(EXCHANGE, s, trend_tf, trend_need)
                    
                    if len(trend_candles) < EMA_TREND_N + 5: continue

                    trend_closes = [c["close"] for c in trend_candles]
                    ema_now = ema(trend_closes, EMA_TREND_N)
                    ema_prev = ema(trend_closes[:-5], EMA_TREND_N)
                    
                    if ema_now is None or ema_prev is None: continue

                    curr_close = float(trend_closes[-1])
                    trend_up = (curr_close > ema_now) and (ema_now > ema_prev)
                    trend_down = (curr_close < ema_now) and (ema_now < ema_prev)

                    # 2) MTF VOLATILITY (ATR)
                    atr_tf = ATR_TF_MAP.get(tf, tf)
                    atr_candles = repo.get_recent_candles(EXCHANGE, s, atr_tf, atr_need)
                    if len(atr_candles) < atr_need: continue
                    
                    atr14 = calc_atr_wilder(atr_candles, ATR_N)
                    if atr14 is None or atr14 <= 0: continue

                    # 3) RESPONSIVE ENTRY (Breakout + Vol Spike)
                    candles = repo.get_recent_candles(EXCHANGE, s, tf, base_need)
                    if len(candles) < base_need: continue

                    last, prev = candles[-1], candles[-2]
                    ts, close, prev_close, volume = last["ts_ms"], float(last["close"]), float(prev["close"]), float(last["volume"])

                    highs = [float(c["high"]) for c in candles[:-1][-BREAKOUT_N:]]
                    lows = [float(c["low"]) for c in candles[:-1][-BREAKOUT_N:]]
                    if not highs or not lows: continue

                    level_hi, level_lo = max(highs), min(lows)

                    breakout_long = close > level_hi and prev_close <= level_hi
                    breakdown_short = close < level_lo and prev_close >= level_lo

                    vols = [float(c["volume"]) for c in candles[:-1][-VOL_AVG_N:]]
                    vol_spike, vol_mult = False, None
                    if vols:
                        avg = mean(vols)
                        if avg > 0:
                            vol_mult = round(volume / avg, 2)
                            if volume > avg * VOL_SPIKE_K: vol_spike = True

                    if not ENABLE_COMBO_ONLY: continue

                    # 4) SETUP INSERTION
                    if breakout_long and vol_spike and trend_up:
                        expires_ts = ts + tf_to_ms(tf) * RETEST_MAX_BARS
                        payload = {"vol_mult": vol_mult, "atr14": round(atr14, 6), "ema200": float(ema_now), "trend_tf": trend_tf, "atr_tf": atr_tf, "entry_ref": close, "level": float(level_hi)}
                        repo.upsert_setup_pending(EXCHANGE, s, tf, "LONG", ts, expires_ts, float(level_hi), payload)
                        repo.insert_signal(EXCHANGE, s, tf, ts, "SETUP_LONG_retest", payload)

                    elif breakdown_short and vol_spike and trend_down:
                        expires_ts = ts + tf_to_ms(tf) * RETEST_MAX_BARS
                        payload = {"vol_mult": vol_mult, "atr14": round(atr14, 6), "ema200": float(ema_now), "trend_tf": trend_tf, "atr_tf": atr_tf, "entry_ref": close, "level": float(level_lo)}
                        repo.upsert_setup_pending(EXCHANGE, s, tf, "SHORT", ts, expires_ts, float(level_lo), payload)
                        repo.insert_signal(EXCHANGE, s, tf, ts, "SETUP_SHORT_retest", payload)

        except Exception as e:
            log_error("Signal ERROR", e)

        shutdown_event.wait(SIGNAL_INTERVAL_SEC)
