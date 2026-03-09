import time
import json
import requests
from collections import OrderedDict
from app.config import *
from app.utils.logging import log_error

# --- HELPER: DYNAMIC PRICE FORMATTER ---
def fmt_px(val):
    if val is None or val == "" or val == 0:
        return "0"
    try:
        v = float(val)
        if v >= 1000: res = f"{v:.2f}"
        elif v >= 10: res = f"{v:.3f}"
        elif v >= 1: res = f"{v:.4f}"
        elif v >= 0.01: res = f"{v:.5f}"
        elif v >= 0.0001: res = f"{v:.6f}"
        else: res = f"{v:.10f}"
        return res.rstrip('0').rstrip('.')
    except Exception:
        return "ERR"

def send_telegram(text: str, reply_to: int = None, chat_id: str = None):
    target_chat = chat_id or TELEGRAM_CHAT_ID
    if not TELEGRAM_BOT_TOKEN or not target_chat:
        return None
    try:
        payload = {
            "chat_id": target_chat, 
            "parse_mode": "HTML", 
            "text": text,
            "allow_sending_without_reply": True
        }
        if reply_to:
            payload["reply_to_message_id"] = reply_to

        r = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json=payload,
            timeout=10
        )
        data = r.json()
        if data.get("ok"):
            return data.get("result", {}).get("message_id")
        return None
    except Exception as e:
        log_error("Telegram ERROR", e)
        return None

def alert_loop(repo, shutdown_event):
    last_id = 0
    cooldown_cache = {}
    thread_cache = OrderedDict()
    retry_queue = {}
    last_cleanup = time.time()

    while not shutdown_event.is_set():
        try:
            now = time.time()

            if now - last_cleanup > 600:
                cooldown_cache = {k: t for k, t in cooldown_cache.items() if t >= now - (ALERT_COOLDOWN_SEC * 2)}
                while len(thread_cache) > 500: thread_cache.popitem(last=False)
                retry_queue = {k: v for k, v in retry_queue.items() if v.get("expires_at", 0) > now}
                while len(retry_queue) > 300: retry_queue.pop(next(iter(retry_queue)))
                last_cleanup = now

            for sid, data in list(retry_queue.items()):
                if now >= data.get("expires_at", now + 1):
                    retry_queue.pop(sid, None)
                    continue

                if now >= data["next_retry"]:
                    fresh_reply_to = None if data["is_setup"] else thread_cache.get(data["thread_key"])
                    sent_msg_id = send_telegram(data["msg"], reply_to=fresh_reply_to, chat_id=TELEGRAM_CHANNEL_ID)
                    
                    if sent_msg_id:
                        if data["is_setup"]: thread_cache[data["thread_key"]] = sent_msg_id
                        elif data["is_close"]: thread_cache.pop(data["thread_key"], None)
                        if not data["is_lifecycle"]: cooldown_cache[data["cache_key"]] = now
                        retry_queue.pop(sid, None)
                    else:
                        retry_queue[sid]["next_retry"] = now + 30

            rows = repo.fetch_new_signals(last_id)
            
            for r in rows:
                signal_id = r["id"]
                last_id = max(last_id, signal_id)

                st, sym, tf = r["signal_type"], r["symbol"], r["timeframe"]
                
                if tf not in TIMEFRAMES:
                    continue

                is_lifecycle = ("PARTIAL" in st) or ("CLOSE" in st) or ("FILL" in st)
                cache_key = f"{sym}|{tf}|{st}"
                thread_key = f"{sym}|{tf}" 

                if not is_lifecycle:
                    if cooldown_cache.get(cache_key) and (now - cooldown_cache.get(cache_key)) < ALERT_COOLDOWN_SEC:
                        continue

                if not repo.mark_alert_sent(r["exchange"], r["symbol"], r["timeframe"], r["ts_ms"], r["signal_type"]):
                    continue

                p = r.get("payload", {})
                if isinstance(p, str):
                    try: p = json.loads(p)
                    except Exception: p = {}

                msg = ""
                if st in ("SETUP_LONG", "SETUP_SHORT"):
                    side = "LONG" if "LONG" in st else "SHORT"
                    icon = "🟢" if side == "LONG" else "🔴"
                    msg = f"{icon} <b>{side} SETUP</b>\n{sym} ({tf})\n\n"
                    msg += f"<b>Entry Zone:</b>\n1) {fmt_px(p.get('entry1',0))}\n2) {fmt_px(p.get('entry2',0))}\n\n"
                    msg += f"<b>Targets:</b>\n1) {fmt_px(p.get('tp1',0))}\n2) {fmt_px(p.get('tp2',0))}\n3) {fmt_px(p.get('tp3',0))}\n\n"
                    msg += f"<b>StopLoss:</b> {fmt_px(p.get('sl',0))}\n\n"
                    msg += f"ATR ({p.get('atr_tf', tf)}): {fmt_px(p.get('atr14',0))}"
                    if p.get("vol_mult"):
                        msg += f"\n💥 Vol Spike: {float(p.get('vol_mult',0)):.2f}x"

                elif "FILL_" in st:
                    side = "LONG" if "LONG" in st else "SHORT"
                    step = "1" if "ENTRY1" in st else "2"
                    msg = f"⚡ <b>{side} FILLED (Step {step})</b>\n{sym} ({tf})\n"
                    msg += f"Filled at: {fmt_px(p.get('entry' + step, 0))}\n"
                    if step == "1" and p.get("fill_mode"):
                        # ✨ KOSMETIK: INSTANT_BREAKOUT diubah jadi AutoFill dengan gaya miring
                        mode_txt = p.get('fill_mode').replace("INSTANT_BREAKOUT", "AutoFill")
                        msg += f"🤖 <i>Mode: {mode_txt}</i>"
                    if step == "2":
                        msg += f"Avg Entry: {fmt_px(p.get('avg_entry',0))}"

                elif st == "PARTIAL_TP1":
                    msg = f"🎯 <b>TP1 HIT</b>\n{sym} ({tf}) - {p.get('side','UNKNOWN')}\n"
                    msg += f"Exit: {fmt_px(p.get('exit',0))}\n"
                    msg += f"Closed Size: {int(float(p.get('closed_pct',0))*100)}%\n"
                    msg += f"Remaining: {int(float(p.get('rem_pct',0))*100)}%\n"
                    msg += f"Realized PnL: {float(p.get('total_pnl',0)):+.2f}%\n"
                    if p.get("sl_moved"): msg += "🛡️ <i>SL moved to Break-Even</i>"

                elif st == "PARTIAL_TP2":
                    msg = f"🎯 <b>TP2 HIT</b>\n{sym} ({tf}) - {p.get('side','UNKNOWN')}\n"
                    msg += f"Exit: {fmt_px(p.get('exit',0))}\n"
                    msg += f"Closed Size: {int(float(p.get('closed_pct',0))*100)}%\n"
                    msg += f"Remaining: {int(float(p.get('rem_pct',0))*100)}%\n"
                    msg += f"Realized PnL: {float(p.get('total_pnl',0)):+.2f}%\n"
                    if p.get("sl_moved_to_tp1"): msg += "🛡️ <i>SL moved to TP1 (Profit Locker)</i>"

                elif "CLOSE" in st:
                    icon = "🏆" if "TP" in st else "💀"
                    side = p.get("side", "UNKNOWN")
                    entry = p.get("entry")
                    close_px = p.get("close_price")
                    total_pnl = float(p.get("total_pnl", 0.0))
                    reason = p.get("reason", st.split("_")[1])

                    msg = f"{icon} <b>TRADE CLOSED ({reason})</b>\n{sym} ({tf}) - {side}\n"
                    if entry and close_px: msg += f"Entry: {fmt_px(entry)}\nFinal Exit: {fmt_px(close_px)}\n"
                    msg += f"<b>Total Realized PnL: {total_pnl:+.2f}%</b>"

                else:
                    msg = f"🔔 {st} | {sym} {tf}"

                if not msg: continue

                reply_to_id = None
                if st not in ("SETUP_LONG", "SETUP_SHORT"): reply_to_id = thread_cache.get(thread_key)

                is_setup = st in ("SETUP_LONG", "SETUP_SHORT")
                is_close = "CLOSE" in st

                sent_msg_id = send_telegram(msg, reply_to=reply_to_id, chat_id=TELEGRAM_CHANNEL_ID)

                if sent_msg_id:
                    if is_setup: thread_cache[thread_key] = sent_msg_id
                    elif is_close: thread_cache.pop(thread_key, None)
                    if not is_lifecycle: cooldown_cache[cache_key] = now
                else:
                    retry_queue[signal_id] = {
                        "msg": msg, "thread_key": thread_key, "is_setup": is_setup, "is_close": is_close,
                        "is_lifecycle": is_lifecycle, "cache_key": cache_key, "next_retry": now + 30, "expires_at": now + 3600
                    }

        except Exception as e:
            log_error("Alert ERROR", e)

        shutdown_event.wait(2)
