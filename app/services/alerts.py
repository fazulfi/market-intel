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
            json={"chat_id": TELEGRAM_CHAT_ID, "parse_mode": "HTML", "text": text},
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

def _safe_float(x):
    try:
        return float(x)
    except Exception:
        return None

def alert_loop(repo, shutdown_event):
    last_id = 0
    cooldown_cache = {}
    last_cleanup = time.time()

    while not shutdown_event.is_set():
        try:
            rows = repo.fetch_new_signals(last_id)
            now = time.time()

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

                if not repo.mark_alert_sent(r["exchange"], r["symbol"], r["timeframe"], r["ts_ms"], r["signal_type"]):
                    continue

                p = _parse_payload(r.get("payload"))
                st = r["signal_type"]

                # --- V1.6 formatting ---
                if "OPEN" in st:
                    icon = "🟢" if "LONG" in st else "🔴"
                    entry = _safe_float(p.get("entry"))
                    tp = _safe_float(p.get("tp"))
                    sl = _safe_float(p.get("sl"))
                    vol_mult = p.get("vol_mult")

                    msg = f"{icon} <b>NEW TRADE OPENED</b>\n{r['symbol']} ({r['timeframe']}) - {st.replace('OPEN_', '')}"
                    if entry is not None and tp is not None and sl is not None:
                        msg += f"\nEntry: {entry:.4f}\nTarget: {tp:.4f}\nStopLoss: {sl:.4f}"
                    if vol_mult:
                        msg += f"\n💥 Vol Spike: {vol_mult}x"

                elif "CLOSE" in st:
                    icon = "🏆" if "TP" in st else "💔"
                    side = (p.get("side") or "UNKNOWN").upper()

                    entry = _safe_float(p.get("entry"))
                    close_px = _safe_float(p.get("close_price"))

                    pnl_str = "N/A"
                    if entry is not None and close_px is not None and entry != 0 and side in ("LONG", "SHORT"):
                        pnl = ((close_px - entry) / entry * 100.0) if side == "LONG" else ((entry - close_px) / entry * 100.0)
                        pnl_str = f"+{pnl:.2f}%" if pnl > 0 else f"{pnl:.2f}%"

                    msg = f"{icon} <b>TRADE CLOSED ({p.get('close_reason')})</b>\n{r['symbol']} ({r['timeframe']}) - {side}"
                    if entry is not None and close_px is not None:
                        msg += f"\nEntry: {entry:.4f}\nClose: {close_px:.4f}"
                    msg += f"\n<b>PnL: {pnl_str}</b>"

                else:
                    msg = f"⚡ {r['symbol']} {r['timeframe']} {st}"

                send_telegram(msg)
                cooldown_cache[cache_key] = now

        except Exception as e:
            log_error("Alert ERROR", e)

        shutdown_event.wait(3)
