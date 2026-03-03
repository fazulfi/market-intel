import ccxt
from app.utils.logging import log

def make_client():
    ex = ccxt.bybit({
        "enableRateLimit": True,
        "options": {"defaultType": "swap"}
    })
    log("Bybit client created")
    return ex
