import json
import time
import threading
import asyncio
import websockets

from app.config import SYMBOLS, ENABLE_WS_TICKER, WS_MARKET_TYPE, WS_PING_SEC, WS_RECONNECT_SEC
from app.utils.logging import log, log_error
from app.utils.memory import set_tick

def _to_bybit_symbol(sym: str) -> str:
    # contoh input bot: "BTC/USDT:USDT" -> "BTCUSDT"
    # fallback aman: hapus semua non-alnum
    s = sym.split(":")[0].replace("/", "")
    return "".join(ch for ch in s if ch.isalnum()).upper()

def BYBIT_WS_PUBLIC_URL -> str:
    # kita pakai linear buat USDT perpetual/futures
    # sesuai docs: wss://stream.bybit.com/v5/public/linear
    if WS_MARKET_TYPE == "linear":
        return "wss://stream.bybit.com/v5/public/linear"
    if WS_MARKET_TYPE == "spot":
        return "wss://stream.bybit.com/v5/public/spot"
    if WS_MARKET_TYPE == "inverse":
        return "wss://stream.bybit.com/v5/public/inverse"
    return "wss://stream.bybit.com/v5/public/linear"

async def _run(shutdown_event: threading.Event):
    url = BYBIT_WS_PUBLIC_URL
    args = [f"tickers.{_to_bybit_symbol(s)}" for s in SYMBOLS]

    sub = {"op": "subscribe", "args": args}

    while not shutdown_event.is_set():
        try:
            log(f"WS Ticker starting url={url} subs={len(args)}")
            async with websockets.connect(url, ping_interval=None, close_timeout=3) as ws:
                await ws.send(json.dumps(sub))

                last_ping = 0.0
                while not shutdown_event.is_set():
                    # heartbeat manual
                    now = time.time()
                    if now - last_ping >= WS_PING_SEC:
                        # Bybit v5 heartbeat packet ("ping")
                        await ws.send(json.dumps({"op": "ping"}))
                        last_ping = now

                    try:
                        msg = await asyncio.wait_for(ws.recv(), timeout=1.0)
                    except asyncio.TimeoutError:
                        continue

                    try:
                        data = json.loads(msg)
                    except Exception:
                        continue

                    topic = data.get("topic", "")
                    if not topic.startswith("tickers."):
                        continue

                    d = data.get("data") or {}
                    # field umum: lastPrice (string)
                    last = d.get("lastPrice") or d.get("last_price") or d.get("last")
                    if last is None:
                        continue

                    bybit_sym = topic.split(".", 1)[1]
                    # simpan pakai key symbol format bot (BTC/USDT:USDT) biar trade_manager gampang
                    # mapping: cari SYMBOLS yg match bybit_sym
                    px = float(last)
                    for orig in SYMBOLS:
                        if _to_bybit_symbol(orig) == bybit_sym:
                            set_tick(orig, px)
                            break

        except Exception as e:
            log_error("WS Ticker ERROR", e)

        # reconnect
        time.sleep(max(1, WS_RECONNECT_SEC))

def start_ws_ticker(shutdown_event: threading.Event):
    if not ENABLE_WS_TICKER:
        return
    try:
        asyncio.run(_run(shutdown_event))
    except Exception:
        # kalau loop async-nya kelempar, biarin main tetap hidup
        pass
