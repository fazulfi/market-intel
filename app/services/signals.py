from statistics import mean
from app.config import *
from app.utils.logging import log_error

_TF_SEC = {"1m":60,"3m":180,"5m":300,"15m":900,"30m":1800,"1h":3600,"4h":14400,"1d":86400}

def ema(values, n):
    if len(values) < n: return None
    k = 2.0 / (n + 1.0)
    e = float(values[0])
    for v in values[1:]: e = (float(v) - e) * k + e
    return e

def calc_atr_wilder(candles, n):
    if len(candles) < n + 1: return None
    trs = [max(float(candles[i]["high"]) - float(candles[i]["low"]), abs(float(candles[i]["high"]) - float(candles[i - 1]["close"])), abs(float(candles[i]["low"]) - float(candles[i - 1]["close"]))) for i in range(1, len(candles))]
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
                    trend_tf, atr_tf = TREND_TF_MAP.get(tf, EMA_TREND_TF), ATR_TF_MAP.get(tf, tf)
                    trend_candles = repo.get_recent_candles(EXCHANGE, s, trend_tf, max(EMA_TREND_N * 2, 400))
                    if len(trend_candles) < EMA_TREND_N + 5: continue
                    
                    trend_closes = [c["close"] for c in trend_candles]
                    ema_now, ema_prev = ema(trend_closes, EMA_TREND_N), ema(trend_closes[:-5], EMA_TREND_N)
                    if not ema_now or not ema_prev: continue
                    
                    curr_close = float(trend_closes[-1])
                    trend_up, trend_down = (curr_close > ema_now and ema_now > ema_prev), (curr_close < ema_now and ema_now < ema_prev)

                    candles = repo.get_recent_candles(EXCHANGE, s, tf, need)
                    if len(candles) < need: continue
                    last, prev = candles[-1], candles[-2]
                    ts, close, prev_close, vol = int(last["ts_ms"]), float(last["close"]), float(prev["close"]), float(last["volume"])

                    highs, lows = [float(c["high"]) for c in candles[:-1][-BREAKOUT_N:]], [float(c["low"]) for c in candles[:-1][-BREAKOUT_N:]]
                    if not highs or not lows: continue
                    level_hi, level_lo = max(highs), min(lows)
                    breakout_long, breakdown_short = (close > level_hi and prev_close <= level_hi), (close < level_lo and prev_close >= level_lo)

                    vols = [float(c["volume"]) for c in candles[:-1][-VOL_AVG_N:]]
                    if not vols or mean(vols) <= 0: continue
                    vol_mult, vol_spike = round(vol / mean(vols), 2), vol > mean(vols) * VOL_SPIKE_K

                    atr_candles = repo.get_recent_candles(EXCHANGE, s, atr_tf, max(ATR_WARMUP, ATR_N + 20))
                    if len(atr_candles) < ATR_N + 2: continue
                    atr14 = calc_atr_wilder(atr_candles, ATR_N)
                    if not atr14 or atr14 <= 0: continue

                    if repo.get_open_trade(EXCHANGE, s, tf) or repo.has_recent_closed_trade_bars(EXCHANGE, s, tf, ts, POST_CLOSE_COOLDOWN_BARS): continue

                    if breakout_long and vol_spike and trend_up:
                        level = float(level_hi)
                        entry1, entry2 = level - (atr14 * ENTRY1_ATR_OFFSET), level - (atr14 * ENTRY2_ATR_OFFSET)
                        sl = level - (atr14 * SL_ATR_MULT)
                        tp1, tp2, tp3 = level + (atr14 * TP1_ATR_MULT), level + (atr14 * TP2_ATR_MULT), level + (atr14 * TP3_ATR_MULT)
                        chase_ok = close >= entry1 and (close - entry1) <= (atr14 * ENTRY1_CHASE_ATR_PCT)

                        payload = {"level": level, "entry1": float(entry1), "entry2": float(entry2), "sl": float(sl), "tp1": float(tp1), "tp2": float(tp2), "tp3": float(tp3), "atr14": round(atr14, 6), "vol_mult": vol_mult, "trend_tf": trend_tf, "atr_tf": atr_tf, "entry1_size": ENTRY1_SIZE, "entry2_size": ENTRY2_SIZE, "instant_fill_entry1": bool(chase_ok), "instant_fill_price": float(close) if chase_ok else None}
                        setup_id = repo.create_layered_setup(EXCHANGE, s, tf, "LONG", ts, ts + (_TF_SEC.get(tf, 60) * 1000 * SETUP_EXPIRY_BARS), payload)
                        if setup_id: repo.insert_signal(EXCHANGE, s, tf, ts, "SETUP_LONG", {"setup_id": setup_id, **payload})

                    elif breakdown_short and vol_spike and trend_down:
                        level = float(level_lo)
                        entry1, entry2 = level + (atr14 * ENTRY1_ATR_OFFSET), level + (atr14 * ENTRY2_ATR_OFFSET)
                        sl = level + (atr14 * SL_ATR_MULT)
                        tp1, tp2, tp3 = level - (atr14 * TP1_ATR_MULT), level - (atr14 * TP2_ATR_MULT), level - (atr14 * TP3_ATR_MULT)
                        chase_ok = close <= entry1 and (entry1 - close) <= (atr14 * ENTRY1_CHASE_ATR_PCT)

                        payload = {"level": level, "entry1": float(entry1), "entry2": float(entry2), "sl": float(sl), "tp1": float(tp1), "tp2": float(tp2), "tp3": float(tp3), "atr14": round(atr14, 6), "vol_mult": vol_mult, "trend_tf": trend_tf, "atr_tf": atr_tf, "entry1_size": ENTRY1_SIZE, "entry2_size": ENTRY2_SIZE, "instant_fill_entry1": bool(chase_ok), "instant_fill_price": float(close) if chase_ok else None}
                        setup_id = repo.create_layered_setup(EXCHANGE, s, tf, "SHORT", ts, ts + (_TF_SEC.get(tf, 60) * 1000 * SETUP_EXPIRY_BARS), payload)
                        if setup_id: repo.insert_signal(EXCHANGE, s, tf, ts, "SETUP_SHORT", {"setup_id": setup_id, **payload})

        except Exception as e: log_error("Signal ERROR", e)
        shutdown_event.wait(SIGNAL_INTERVAL_SEC)
