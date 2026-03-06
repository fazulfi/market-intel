import asyncio
import json
import websockets

from app.config import (ENABLE_WS_KLINES, BYBIT_WS_PUBLIC_URL, WS_KLINE_TIMEFRAMES, SYMBOLS, EXCHANGE)
from app.db.repo import Repo
from app.utils.bybit_map import ccxt_symbol_to_bybit, tf_to_bybit
from app.utils.logging import log, log_error

def _find_ccxt_symbol(bybit_sym: str):
    for s in SYMBOLS:
        if ccxt_symbol_to_bybit(s) == bybit_sym: return s
    return None

def _find_tf(interval: str):
    for tf in WS_KLINE_TIMEFRAMES:
        if tf_to_bybit(tf) == interval: return tf
    return None

async def klines_loop(shutdown_event):
    if not ENABLE_WS_KLINES: return
    repo = Repo()
    topics = [f"kline.{tf_to_bybit(tf)}.{ccxt_symbol_to_bybit(sym)}" for sym in SYMBOLS for tf in WS_KLINE_TIMEFRAMES]
    sub_msg = {"op": "subscribe", "args": topics}

    log(f"WS_KLINES starting, topics={len(topics)}")

    while not shutdown_event.is_set():
        try:
            async with websockets.connect(BYBIT_WS_PUBLIC_URL, ping_interval=20) as ws:
                for i in range(0, len(topics), 25):
                    await ws.send(json.dumps({"op": "subscribe", "args": topics[i:i+25]}))
                    import asyncio
                    await asyncio.sleep(0.1)
                log(f"WS_KLINES subscribed to {len(topics)} topics in batches")

                while not shutdown_event.is_set():
                    raw = await ws.recv()
                    msg = json.loads(raw)

                    topic = msg.get("topic", "")
                    if not topic.startswith("kline."): continue

                    parts = topic.split(".")
                    if len(parts) < 3: continue

                    interval, bybit_sym = parts[1], parts[2]
                    sym = _find_ccxt_symbol(bybit_sym)
                    tf = _find_tf(interval)
                    if not sym or not tf: continue

                    data = msg.get("data")
                    if not data: continue
                    if isinstance(data, dict): data = [data]

                    for k in data:
                        if k.get("confirm") is not True: continue

                        ts_ms = int(k.get("start") or k.get("t") or 0)
                        if not ts_ms: continue
                        if ts_ms < 10_000_000_000: ts_ms *= 1000

                        try:
                            o, h, l, c, v = float(k.get("open") or k.get("o")), float(k.get("high") or k.get("h")), float(k.get("low") or k.get("l")), float(k.get("close") or k.get("c")), float(k.get("volume") or k.get("v") or 0)
                            await asyncio.to_thread(repo.upsert_candles, EXCHANGE, sym, tf, [[ts_ms, o, h, l, c, v]])
                        except Exception: continue
        except Exception as e:
            log_error("WS_KLINES ERROR", e)
            await asyncio.sleep(3)

def start_ws_klines(shutdown_event):
    try: asyncio.run(klines_loop(shutdown_event))
    except Exception: pass
