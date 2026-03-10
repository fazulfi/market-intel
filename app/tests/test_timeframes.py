from app.utils.timeframes import smallest_tf

def test_smallest_tf_basic():
    # Harus mengembalikan 1m karena itu yang paling kecil
    assert smallest_tf(["5m", "15m", "1m"]) == "1m"

def test_smallest_tf_no_1m():
    # Harus mengembalikan 5m
    assert smallest_tf(["15m", "5m", "1h"]) == "5m"

def test_smallest_tf_empty():
    # Kalau kosong, fallback ke 1m
    assert smallest_tf([]) == "1m"
    assert smallest_tf(None) == "1m"

def test_smallest_tf_invalid():
    # Mengabaikan input ngawur
    assert smallest_tf(["ngawur", "15m"]) == "15m"
