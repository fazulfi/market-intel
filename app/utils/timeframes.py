def smallest_tf(timeframes):
    tf_sec = {"1m":60,"3m":180,"5m":300,"15m":900,"30m":1800,"1h":3600,"4h":14400,"1d":86400}
    xs = [tf for tf in (timeframes or []) if tf in tf_sec]
    return min(xs, key=lambda t: tf_sec[t]) if xs else "1m"
