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

                    highs = [c["high"] for c in candles[:-1][-BREAKOUT_N:]]
                    if highs and last["close"] > max(highs) and prev["close"] <= max(highs):
                        repo.insert_signal(EXCHANGE, s, tf, last["ts_ms"], "breakout", {})

                    vols = [c["volume"] for c in candles[:-1][-VOL_AVG_N:]]
                    if vols and last["volume"] > mean(vols) * VOL_SPIKE_K:
                        repo.insert_signal(EXCHANGE, s, tf, last["ts_ms"], "vol_spike", {})

        except Exception as e:
            log_error("Signal ERROR", e)

        shutdown_event.wait(SIGNAL_INTERVAL_SEC)
