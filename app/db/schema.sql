CREATE TABLE IF NOT EXISTS candles (
  exchange TEXT NOT NULL,
  symbol TEXT NOT NULL,
  timeframe TEXT NOT NULL,
  ts_ms BIGINT NOT NULL,
  open DOUBLE PRECISION NOT NULL,
  high DOUBLE PRECISION NOT NULL,
  low DOUBLE PRECISION NOT NULL,
  close DOUBLE PRECISION NOT NULL,
  volume DOUBLE PRECISION NOT NULL,
  inserted_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (exchange, symbol, timeframe, ts_ms)
);

CREATE TABLE IF NOT EXISTS signals (
  id BIGSERIAL PRIMARY KEY,
  exchange TEXT NOT NULL,
  symbol TEXT NOT NULL,
  timeframe TEXT NOT NULL,
  ts_ms BIGINT NOT NULL,
  signal_type TEXT NOT NULL,
  payload JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (exchange, symbol, timeframe, ts_ms, signal_type)
);

CREATE TABLE IF NOT EXISTS alerts (
  id BIGSERIAL PRIMARY KEY,
  exchange TEXT NOT NULL,
  symbol TEXT NOT NULL,
  timeframe TEXT NOT NULL,
  ts_ms BIGINT NOT NULL,
  signal_type TEXT NOT NULL,
  sent_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (exchange, symbol, timeframe, ts_ms, signal_type)
);

-- --- V1.6 TRADES TABLE ---
CREATE TABLE IF NOT EXISTS trades (
  id BIGSERIAL PRIMARY KEY,
  exchange TEXT NOT NULL,
  symbol TEXT NOT NULL,
  timeframe TEXT NOT NULL,
  side TEXT NOT NULL,
  status TEXT NOT NULL,
  opened_ts_ms BIGINT NOT NULL,
  entry DOUBLE PRECISION NOT NULL,
  tp DOUBLE PRECISION NOT NULL,
  sl DOUBLE PRECISION NOT NULL,
  atr14 DOUBLE PRECISION,
  vol_mult DOUBLE PRECISION,
  level DOUBLE PRECISION,
  closed_ts_ms BIGINT,
  close_price DOUBLE PRECISION,
  close_reason TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  closed_at TIMESTAMPTZ
);

CREATE UNIQUE INDEX IF NOT EXISTS one_open_trade_per_pair ON trades(exchange, symbol, timeframe) WHERE status = 'OPEN';
CREATE INDEX IF NOT EXISTS trades_lookup ON trades(exchange, symbol, timeframe, status);
