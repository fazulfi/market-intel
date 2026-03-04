import time
import json
import requests
from app.config import *
from app.utils.logging import log_error

def send_telegram(text: str):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": text},
            timeout=10,
        )
    except Exception as e:
        log_error("Telegram ERROR", e)

def _parse_payload(p):
    if not p:
        return {}
    if isinstance(p, dict):
        return p
    if isinstance(p, str):
        try:
            return json.loads(p)
        except Exception:
            return {}
    return {}

def alert_loop(repo, shutdown_event):
    last_id = 0
    cooldown_cache = {}
    last_cleanup = time.time()

    while not shutdown_event.is_set():
        try:
            rows = repo.fetch_new_signals(last_id)
            now = time.time()

            # cleanup cache tiap 10 menit
            if now - last_cleanup > 600:
                expiry = now - (ALERT_COOLDOWN_SEC * 2)
                cooldown_cache = {k: t for k, t in cooldown_cache.items() if t >= expiry}
                last_cleanup = now

            for r in rows:
                last_id = r["id"]

                cache_key = f"{r['symbol']}|{r['timeframe']}|{r['signal_type']}"
                last_sent = cooldown_cache.get(cache_key)
                if last_sent and (now - last_sent) < ALERT_COOLDOWN_SEC:
                    continue

                if not repo.mark_alert_sent(
                    r["exchange"], r["symbol"], r["timeframe"], r["ts_ms"], r["signal_type"]
                ):
                    continue

                payload = _parse_payload(r.get("payload"))

                st = r["signal_type"]
                icon = "🟢" if "LONG" in st else "🔴" if "SHORT" in st else "⚡"

                vol_mult = payload.get("vol_mult")
                entry = payload.get("entry")
                sl = payload.get("sl")
                tp = payload.get("tp")
                atr14 = payload.get("atr14")

                msg = f"{icon} {r['symbol']} {r['timeframe']} {st}"

                if vol_mult:
                    msg += f"\n💥 VOL: {vol_mult}x"

                if entry is not None and sl is not None and tp is not None:
                    msg += f"\n\n🎯 SETUP (RR 2:1)"
                    msg += f"\nEntry: {float(entry):.4f}"
                    msg += f"\nTP: {float(tp):.4f}"
                    msg += f"\nSL: {float(sl):.4f}"
                    if atr14 is not None:
                        msg += f"\nATR14: {float(atr14):.4f}"

                send_telegram(msg)
                cooldown_cache[cache_key] = now

        except Exception as e:
            log_error("Alert ERROR", e)

        shutdown_event.wait(3)
