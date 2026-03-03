from datetime import datetime, timezone
import traceback

def log(msg):
    ts = datetime.now(timezone.utc).isoformat()
    print(f"[{ts}] {msg}", flush=True)

def log_error(prefix, e):
    log(f"{prefix}: {e}")
    traceback.print_exc()
