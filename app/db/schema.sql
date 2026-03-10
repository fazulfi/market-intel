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

-- --- V2.5+ TRADES TABLE (UPDATED SCHEMA) ---
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
  
  -- V2 Layered Entry & TP Columns
  entry1 DOUBLE PRECISION,
  entry2 DOUBLE PRECISION,
  entry1_size DOUBLE PRECISION,
  entry2_size DOUBLE PRECISION,
  filled_entry2 BOOLEAN DEFAULT false,
  avg_entry DOUBLE PRECISION,
  tp1 DOUBLE PRECISION,
  tp2 DOUBLE PRECISION,
  tp3 DOUBLE PRECISION,
  remaining_size_pct DOUBLE PRECISION DEFAULT 1.0,
  realized_pnl_pct DOUBLE PRECISION DEFAULT 0.0,
  tp1_hit BOOLEAN DEFAULT false,
  tp2_hit BOOLEAN DEFAULT false,
  tp3_hit BOOLEAN DEFAULT false,
  
  closed_ts_ms BIGINT,
  close_price DOUBLE PRECISION,
  close_reason TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  closed_at TIMESTAMPTZ
);

CREATE UNIQUE INDEX IF NOT EXISTS one_open_trade_per_pair ON trades(exchange, symbol, timeframe) WHERE status = 'OPEN';
CREATE INDEX IF NOT EXISTS trades_lookup ON trades(exchange, symbol, timeframe, status);

-- --- V2.4+ TRADE SETUPS (UPDATED SCHEMA) ---
CREATE TABLE IF NOT EXISTS trade_setups (
  id BIGSERIAL PRIMARY KEY,
  exchange TEXT NOT NULL,
  symbol TEXT NOT NULL,
  timeframe TEXT NOT NULL,
  side TEXT NOT NULL,                
  status TEXT NOT NULL,              
  created_ts_ms BIGINT NOT NULL,
  expires_ts_ms BIGINT NOT NULL,
  level DOUBLE PRECISION NOT NULL,
  payload JSONB NOT NULL,
  
  -- V2 Setup Fields
  entry1 DOUBLE PRECISION,
  entry2 DOUBLE PRECISION,
  sl DOUBLE PRECISION,
  tp1 DOUBLE PRECISION,
  tp2 DOUBLE PRECISION,
  tp3 DOUBLE PRECISION,
  atr14 DOUBLE PRECISION,
  filled_entry1 BOOLEAN DEFAULT false,
  filled_entry2 BOOLEAN DEFAULT false,
  avg_entry DOUBLE PRECISION,
  entry1_size DOUBLE PRECISION,
  entry2_size DOUBLE PRECISION,

  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS one_pending_setup_per_pair
ON trade_setups(exchange, symbol, timeframe)
WHERE status = 'PENDING';
