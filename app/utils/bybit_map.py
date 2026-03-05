def ccxt_symbol_to_bybit(sym: str) -> str:
    # Mengubah "BTC/USDT:USDT" -> "BTCUSDT"
    return sym.replace(":USDT", "").replace("/", "")

_TF_TO_MIN = {
    "1m": "1",
    "3m": "3",
    "5m": "5",
    "15m": "15",
    "30m": "30",
    "1h": "60",
    "2h": "120",
    "4h": "240",
    "1d": "D",
}

def tf_to_bybit(tf: str) -> str:
    # Mengubah "1h" -> "60" sesuai aturan Bybit
    return _TF_TO_MIN.get(tf, "1")
