import time
import json
import requests
from app.config import *
from app.utils.logging import log_error

def send_telegram(text: str):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID: return
    try: requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage", json={"chat_id": TELEGRAM_CHAT_ID, "parse_mode": "HTML", "text": text}, timeout=10)
    except Exception as e: log_error("Telegram ERROR", e)

def alert_loop(repo, shutdown_event):
    last_id = 0
    cooldown_cache, last_cleanup = {}, time.time()

    while not shutdown_event.is_set():
        try:
            rows = repo.fetch_new_signals(last_id)
            now = time.time()
            if now - last_cleanup > 600:
                cooldown_cache = {k: t for k, t in cooldown_cache.items() if t >= now - (ALERT_COOLDOWN_SEC * 2)}
                last_cleanup = now

            for r in rows:
                last_id = r["id"]
                cache_key = f"{r['symbol']}|{r['timeframe']}|{r['signal_type']}"
                if cooldown_cache.get(cache_key) and (now - cooldown_cache.get(cache_key)) < ALERT_COOLDOWN_SEC: continue
                if not repo.mark_alert_sent(r["exchange"], r["symbol"], r["timeframe"], r["ts_ms"], r["signal_type"]): continue

                st, sym, tf = r["signal_type"], r["symbol"], r["timeframe"]
                p = r.get("payload", {})
                if isinstance(p, str): 
                    try: p = json.loads(p)
                    except: p = {}

                # 💎 THE VIP SIGNAL FORMAT 💎
                if st in ("SETUP_LONG", "SETUP_SHORT"):
                    side = "LONG" if "LONG" in st else "SHORT"
                    icon = "🟢" if side == "LONG" else "🔴"
                    msg = f"{icon} <b>{side} SETUP</b>\n{sym} ({tf})\n\n"
                    msg += f"<b>Entry Zone:</b>\n1) {float(p.get('entry1',0)):.4f}\n2) {float(p.get('entry2',0)):.4f}\n\n"
                    msg += f"<b>Targets:</b>\n1) {float(p.get('tp1',0)):.4f}\n2) {float(p.get('tp2',0)):.4f}\n3) {float(p.get('tp3',0)):.4f}\n\n"
                    msg += f"<b>StopLoss:</b> {float(p.get('sl',0)):.4f}\n\n"
                    msg += f"ATR ({p.get('atr_tf', tf)}): {float(p.get('atr14',0)):.4f}"
                    if p.get("vol_mult"): msg += f"\n💥 Vol Spike: {float(p.get('vol_mult',0)):.2f}x"
                
                elif "FILL_" in st:
                    side = "LONG" if "LONG" in st else "SHORT"
                    step = "1" if "ENTRY1" in st else "2"
                    msg = f"⚡ <b>{side} FILLED (Step {step})</b>\n{sym} ({tf})\nFilled at: {float(p.get('entry'+step,0)):.4f}"
                    if step == "2": msg += f"\nAvg Entry: {float(p.get('avg_entry',0)):.4f}"

                elif "CLOSE" in st:
                    icon, side = ("🏆" if "TP" in st else "💀"), (p.get("side") or "UNKNOWN").upper()
                    entry, close_px = p.get("entry"), p.get("close_price")
                    pnl_str = "N/A"
                    if entry and close_px and entry != 0 and side in ("LONG", "SHORT"):
                        pnl = ((close_px - entry) / entry * 100.0) if side == "LONG" else ((entry - close_px) / entry * 100.0)
                        pnl_str = f"+{pnl:.2f}%" if pnl > 0 else f"{pnl:.2f}%"
                    msg = f"{icon} <b>TRADE CLOSED ({p.get('close_reason', 'UNKNOWN')})</b>\n{sym} ({tf}) - {side}"
                    if entry and close_px: msg += f"\nEntry: {float(entry):.4f}\nClose: {float(close_px):.4f}"
                    msg += f"\n<b>PnL: {pnl_str}</b>"
                else:
                    msg = f"🔔 {st} | {sym} {tf}"

                send_telegram(msg)
                cooldown_cache[cache_key] = now

        except Exception as e: log_error("Alert ERROR", e)
        shutdown_event.wait(3)
