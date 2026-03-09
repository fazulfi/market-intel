from datetime import datetime, timezone
import traceback

# === ANSI COLOR CODES ===
RESET = "\033[0m"
GRAY = "\033[90m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
CYAN = "\033[96m"
MAGENTA = "\033[95m"
WHITE = "\033[97m"

def log(msg):
    # Memperpendek format waktu agar tidak memenuhi layar (Contoh: 26-03-09 10:15:30)
    ts = datetime.now(timezone.utc).strftime("%y-%m-%d %H:%M:%S")
    
    # Deteksi otomatis warna berdasarkan kata kunci!
    msg_upper = msg.upper()
    
    if "ERROR" in msg_upper or "FAIL" in msg_upper or "DITOLAK" in msg_upper:
        color = RED
    elif "HEALTH OK" in msg_upper:
        color = MAGENTA  # Detak jantung warna pink/ungu
    elif "STARTING" in msg_upper or "CONNECTED" in msg_upper or "COMPLETE" in msg_upper:
        color = GREEN    # Status sukses warna hijau
    elif "SUBSCRIBED" in msg_upper or "BACKFILL" in msg_upper or "TOPICS" in msg_upper:
        color = CYAN     # Aktivitas data warna biru muda
    elif "⚠️" in msg or "WARN" in msg_upper:
        color = YELLOW   # Peringatan warna kuning
    else:
        color = WHITE    # Default

    # Cetak log dengan warna yang sudah diatur
    print(f"{GRAY}[{ts}]{RESET} {color}{msg}{RESET}", flush=True)

def log_error(prefix, e):
    ts = datetime.now(timezone.utc).strftime("%y-%m-%d %H:%M:%S")
    print(f"{GRAY}[{ts}]{RESET} {RED}❌ {prefix}: {e}{RESET}", flush=True)
    
    # Cetak Traceback (Detail Error) dengan warna merah redup agar tidak menyilaukan
    print(f"\033[31m", end="")
    traceback.print_exc()
    print(f"{RESET}", end="", flush=True)
