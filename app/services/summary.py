from datetime import datetime, timezone
from app.config import *
from app.utils.logging import log_error, log
from app.services.alerts import send_telegram

def _utc_now():
    return datetime.now(timezone.utc)

def _fmt_stats(title: str, s: dict, open_count: int) -> str:
    closed = int(s.get("closed", 0) or 0)
    wins = int(s.get("wins", 0) or 0)
    losses = int(s.get("losses", 0) or 0)
    avg_pnl = float(s.get("avg_pnl", 0) or 0)
    sum_pnl = float(s.get("sum_pnl", 0) or 0)
    wr = (wins / closed * 100.0) if closed > 0 else 0.0

    msg = []
    msg.append(f"📊 {title}")
    msg.append(f"Closed: {closed} | Win: {wins} | Loss: {losses} | WR: {wr:.1f}%")
    msg.append(f"Avg PnL: {avg_pnl:+.3f}% | Sum PnL: {sum_pnl:+.3f}%")
    msg.append(f"Open trades now: {open_count}")
    return "\n".join(msg)

def summary_loop(repo, shutdown_event):
    log("Summary service V1.7 starting")

    last_hour_key = None
    last_day_key = None

    while not shutdown_event.is_set():
        try:
            now = _utc_now()
            open_count = repo.fetch_open_trades_count()

            # hourly: once per hour when minute matches
            hour_key = (now.year, now.month, now.day, now.hour)
            if now.minute == SUMMARY_HOURLY_MINUTE and hour_key != last_hour_key:
                s = repo.fetch_trade_stats_window(3600)
                send_telegram(_fmt_stats("Hourly Summary (last 1h)", s, open_count))
                last_hour_key = hour_key

            # daily: once per day when hour+minute matches
            day_key = (now.year, now.month, now.day)
            if (now.hour == SUMMARY_DAILY_HOUR and now.minute == SUMMARY_DAILY_MINUTE and day_key != last_day_key):
                s = repo.fetch_trade_stats_window(86400)
                send_telegram(_fmt_stats("Daily Summary (last 24h)", s, open_count))
                last_day_key = day_key

        except Exception as e:
            log_error("Summary ERROR", e)

        shutdown_event.wait(1)
