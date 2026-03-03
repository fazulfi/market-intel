from app.config import HEARTBEAT_INTERVAL_SEC
from app.utils.logging import log

def heartbeat_loop(shutdown_event):
    while not shutdown_event.is_set():
        log("HEALTH OK")
        shutdown_event.wait(HEARTBEAT_INTERVAL_SEC)
