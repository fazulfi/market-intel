import logging
import os
import sys
from logging.handlers import RotatingFileHandler

# Ambil identitas dari .env
BOT_NAME = os.getenv("BOT_NAME", "GhostBot")

LOG_DIR = "logs"
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

logger = logging.getLogger(BOT_NAME)
logger.setLevel(logging.INFO)

if logger.hasHandlers():
    logger.handlers.clear()

# --- THE MAGIC WAND: COLOR FORMATTER ---
class ColoredFormatter(logging.Formatter):
    # ANSI escape codes
    CYAN = "\033[96m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    RESET = "\033[0m"

    def format(self, record):
        # Pilih warna berdasarkan level (Hijau=INFO, Merah=ERROR, Kuning=WARN)
        if record.levelno == logging.DEBUG:
            color = self.CYAN
        elif record.levelno == logging.INFO:
            color = self.GREEN
        elif record.levelno == logging.WARNING:
            color = self.YELLOW
        elif record.levelno >= logging.ERROR:
            color = self.RED
        else:
            color = self.RESET

        # Rakit teks dengan warna
        format_str = f"{color}%(asctime)s | %(levelname)-8s | [{BOT_NAME}] %(message)s{self.RESET}"
        formatter = logging.Formatter(format_str, datefmt='%Y-%m-%d %H:%M:%S')
        return formatter.format(record)

plain_formatter = logging.Formatter(
    fmt=f'%(asctime)s | %(levelname)-8s | [{BOT_NAME}] %(message)s', 
    datefmt='%Y-%m-%d %H:%M:%S'
)

# 1. FILE HANDLER (TETAP POLOS AGAR FILE .LOG BERSIH)
safe_bot_name = BOT_NAME.replace(" ", "_").lower()
file_handler = RotatingFileHandler(
    os.path.join(LOG_DIR, f"{safe_bot_name}.log"), 
    maxBytes=5*1024*1024, 
    backupCount=3
)
file_handler.setFormatter(plain_formatter)
logger.addHandler(file_handler)

# 2. CONSOLE HANDLER (BERWARNA UNTUK MATA KAPTEN!)
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(ColoredFormatter())
logger.addHandler(console_handler)

def log(msg: str):
    logger.info(msg)

def log_error(context: str, e: Exception):
    logger.error(f"{context}: {e}", exc_info=True)

def log_debug(msg: str):
    logger.debug(msg)

def log_warning(msg: str):
    logger.warning(msg)
