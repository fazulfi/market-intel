import requests
from app.config import *
from app.utils.logging import log_error

def send_telegram(text):
    if not TELEGRAM_BOT_TOKEN:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": text},
            timeout=10
        )
    except Exception as e:
        log_error("Telegram ERROR", e)

def alert_loop(repo, shutdown_event):
    last_id = 0

    while not shutdown_event.is_set():
        try:
            rows = repo.fetch_new_signals(last_id)
            for r in rows:
                last_id = r["id"]
                if not repo.mark_alert_sent(
                    r["exchange"], r["symbol"],
                    r["timeframe"], r["ts_ms"],
                    r["signal_type"]
                ):
                    continue

                send_telegram(
                    f"{r['symbol']} {r['timeframe']} {r['signal_type']}"
                )
        except Exception as e:
            log_error("Alert ERROR", e)

        shutdown_event.wait(3)
