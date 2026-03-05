from threading import Lock

_lock = Lock()
_tick_last = {}

def set_tick(symbol: str, price: float):
    with _lock:
        _tick_last[symbol] = float(price)

def get_tick(symbol: str):
    with _lock:
        return _tick_last.get(symbol)
