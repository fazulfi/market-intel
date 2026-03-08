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
            timeout=10
        )
    except Exception as e:
        log_error("Telegram ERROR", e)

def alert_loop(repo, shutdown_event):
    last_id = 0
    cooldown_cache = {}
    last_cleanup = time.time()

    while not shutdown_event.is_set():
        try:
            rows = repo.fetch_new_signals(last_id)
            now = time.time()

            if now - last_cleanup > 600:
                cooldown_cache = {k: t for k, t in cooldown_cache.items() if t >= now - (ALERT_COOLDOWN_SEC * 2)}
                last_cleanup = now

            for r in rows:
                last_id = r["id"]
                st, sym, tf = r["signal_type"], r["symbol"], r["timeframe"]

                is_lifecycle = ("PARTIAL" in st) or ("CLOSE" in st) or ("FILL" in st)
                cache_key = f"{sym}|{tf}|{st}"

                if not is_lifecycle:
                    if cooldown_cache.get(cache_key) and (now - cooldown_cache.get(cache_key)) < ALERT_COOLDOWN_SEC:
                        continue

                if not repo.mark_alert_sent(r["exchange"], r["symbol"], r["timeframe"], r["ts_ms"], r["signal_type"]):
                    continue

                p = r.get("payload", {})
                if isinstance(p, str):
                    try:
                        p = json.loads(p)
                    except Exception:
                        p = {}

                if st in ("SETUP_LONG", "SETUP_SHORT"):
                    side = "LONG" if "LONG" in st else "SHORT"
                    icon = "🟢" if side == "LONG" else "🔴"
                    msg = f"{icon} <b>{side} SETUP</b>\n{sym} ({tf})\n\n"
                    msg += f"<b>Entry Zone:</b>\n1) {float(p.get('entry1',0)):.4f}\n2) {float(p.get('entry2',0)):.4f}\n\n"
                    msg += f"<b>Targets:</b>\n1) {float(p.get('tp1',0)):.4f}\n2) {float(p.get('tp2',0)):.4f}\n3) {float(p.get('tp3',0)):.4f}\n\n"
                    msg += f"<b>StopLoss:</b> {float(p.get('sl',0)):.4f}\n\n"
                    msg += f"ATR ({p.get('atr_tf', tf)}): {float(p.get('atr14',0)):.4f}"
                    if p.get("vol_mult"):
                        msg += f"\n💥 Vol Spike: {float(p.get('vol_mult',0)):.2f}x"

                elif "FILL_" in st:
                    side = "LONG" if "LONG" in st else "SHORT"
                    step = "1" if "ENTRY1" in st else "2"
                    msg = f"⚡ <b>{side} FILLED (Step {step})</b>\n{sym} ({tf})\n"
                    msg += f"Filled at: {float(p.get('entry' + step, 0)):.4f}"
                    if step == "1" and p.get("fill_mode"):
                        msg += f"\nMode: {p.get('fill_mode')}"
                    if step == "2":
                        msg += f"\nAvg Entry: {float(p.get('avg_entry',0)):.4f}"

                elif st == "PARTIAL_TP1":
                    msg = f"🎯 <b>TP1 HIT</b>\n{sym} ({tf}) - {p.get('side','UNKNOWN')}\n"
                    msg += f"Exit: {float(p.get('exit',0)):.4f}\n"
                    msg += f"Closed Size: {int(float(p.get('closed_pct',0))*100)}%\n"
                    msg += f"Remaining: {int(float(p.get('rem_pct',0))*100)}%\n"
                    msg += f"Realized PnL: {float(p.get('total_pnl',0)):+.2f}%\n"
                    if p.get("sl_moved"):
                        msg += "🛡️ <i>SL moved to Break-Even</i>"

                elif st == "PARTIAL_TP2":
                    msg = f"🎯 <b>TP2 HIT</b>\n{sym} ({tf}) - {p.get('side','UNKNOWN')}\n"
                    msg += f"Exit: {float(p.get('exit',0)):.4f}\n"
                    msg += f"Closed Size: {int(float(p.get('closed_pct',0))*100)}%\n"
                    msg += f"Remaining: {int(float(p.get('rem_pct',0))*100)}%\n"
                    msg += f"Realized PnL: {float(p.get('total_pnl',0)):+.2f}%\n"
                    if p.get("sl_moved_to_tp1"):
                        msg += "🛡️ <i>SL moved to TP1 (Profit Locker)</i>"

                elif "CLOSE" in st:
                    icon = "🏆" if "TP" in st else "💀"
                    side = p.get("side", "UNKNOWN")
                    entry = p.get("entry")
                    close_px = p.get("close_price")
                    total_pnl = float(p.get("total_pnl", 0.0))
                    reason = p.get("reason", st.split("_")[1])

                    msg = f"{icon} <b>TRADE CLOSED ({reason})</b>\n{sym} ({tf}) - {side}\n"
                    if entry and close_px:
                        msg += f"Entry: {float(entry):.4f}\nFinal Exit: {float(close_px):.4f}\n"
                    msg += f"<b>Total Realized PnL: {total_pnl:+.2f}%</b>"

                else:
                    msg = f"🔔 {st} | {sym} {tf}"

                send_telegram(msg)
                if not is_lifecycle:
                    cooldown_cache[cache_key] = now

        except Exception as e:
            log_error("Alert ERROR", e)

        shutdown_event.wait(2)
