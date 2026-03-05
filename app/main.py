import threading
import signal
import sys
from app.db.repo import Repo
from app.exchanges.bybit import make_client
from app.services.collector import collect_loop
from app.services.signals import signal_loop
from app.services.alerts import alert_loop
from app.services.backfill import run_backfill
from app.services.trade_manager import trade_manager_loop
from app.services.retest_manager import retest_manager_loop
from app.services.summary import summary_loop
from app.utils.heartbeat import heartbeat_loop
from app.utils.logging import log

shutdown_event = threading.Event()

def handle_shutdown(sig, frame):
    log("Graceful shutdown triggered")
    shutdown_event.set()

def main():
    signal.signal(signal.SIGTERM, handle_shutdown)
    signal.signal(signal.SIGINT, handle_shutdown)

    log("Market Intel V1.7 starting")

    repo = Repo()
    repo.init_schema()
    ex = make_client()

    run_backfill(repo, ex)

    threads = [
        threading.Thread(target=collect_loop, args=(repo, ex, shutdown_event), daemon=True),
        threading.Thread(target=signal_loop, args=(repo, shutdown_event), daemon=True),
        threading.Thread(target=trade_manager_loop, args=(repo, shutdown_event), daemon=True),
        threading.Thread(target=alert_loop, args=(repo, shutdown_event), daemon=True),
        threading.Thread(target=summary_loop, args=(repo, shutdown_event), daemon=True),
        threading.Thread(target=retest_manager_loop, args=(repo, shutdown_event), daemon=True),
        threading.Thread(target=heartbeat_loop, args=(shutdown_event,), daemon=True),
    ]

    for t in threads:
        t.start()

    shutdown_event.wait()

    for t in threads:
        t.join()

    log("Shutdown complete")
    sys.exit(0)

if __name__ == "__main__":
    main()
