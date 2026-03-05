import time
import json
from psycopg_pool import ConnectionPool
from psycopg.rows import dict_row
from app.config import DB_DSN
from app.utils.logging import log

class Repo:
    def __init__(self):
        self.pool = self._init_pool()

    def _init_pool(self):
        while True:
            try:
                pool = ConnectionPool(conninfo=DB_DSN, min_size=1, max_size=10, kwargs={"row_factory": dict_row})
                with pool.connection() as conn:
                    conn.execute("SELECT 1;")
                log("PostgreSQL connected (pool ready)")
                return pool
            except Exception as e:
                log(f"Waiting DB... {e}")
                time.sleep(2)

    def init_schema(self):
        from pathlib import Path
        schema_path = Path(__file__).parent / "schema.sql"
        sql = schema_path.read_text()
        with self.pool.connection() as conn:
            conn.execute(sql)

    def upsert_candles(self, exchange, symbol, tf, candles):
        sql = """
        INSERT INTO candles (exchange,symbol,timeframe,ts_ms,open,high,low,close,volume)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING;
        """
        rows = [(exchange, symbol, tf, *c) for c in candles]
        with self.pool.connection() as conn:
            with conn.cursor() as cur:
                cur.executemany(sql, rows)

    def get_recent_candles(self, exchange, symbol, tf, limit):
        sql = "SELECT ts_ms,open,high,low,close,volume FROM candles WHERE exchange=%s AND symbol=%s AND timeframe=%s ORDER BY ts_ms DESC LIMIT %s;"
        with self.pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (exchange, symbol, tf, limit))
                rows = cur.fetchall()
        return list(reversed(rows))

    def insert_signal(self, exchange, symbol, tf, ts, stype, payload):
        sql = """
        INSERT INTO signals (exchange, symbol, timeframe, ts_ms, signal_type, payload)
        VALUES (%s,%s,%s,%s,%s,%s::jsonb) ON CONFLICT (exchange, symbol, timeframe, ts_ms, signal_type) DO NOTHING;
        """
        with self.pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (exchange, symbol, tf, ts, stype, json.dumps(payload)))

    def fetch_new_signals(self, last_id):
        sql = "SELECT * FROM signals WHERE id > %s ORDER BY id ASC LIMIT 100;"
        with self.pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (last_id,))
                return cur.fetchall()

    def mark_alert_sent(self, exchange, symbol, tf, ts, stype):
        sql = "INSERT INTO alerts (exchange,symbol,timeframe,ts_ms,signal_type) VALUES (%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING;"
        with self.pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (exchange, symbol, tf, ts, stype))
                return cur.rowcount == 1

    # --- V1.6 TRADE METHODS ---
    def get_open_trade(self, exchange, symbol, tf):
        sql = "SELECT * FROM trades WHERE exchange=%s AND symbol=%s AND timeframe=%s AND status='OPEN' ORDER BY id DESC LIMIT 1;"
        with self.pool.connection() as conn:
            row = conn.execute(sql, (exchange, symbol, tf)).fetchone()
            return dict(row) if row else None

    def open_trade(self, exchange, symbol, tf, side, opened_ts_ms, payload: dict):
        sql = """
        INSERT INTO trades (exchange, symbol, timeframe, side, status, opened_ts_ms, entry, tp, sl, atr14, vol_mult, level)
        VALUES (%s,%s,%s,%s,'OPEN',%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING RETURNING id;
        """
        with self.pool.connection() as conn:
            r = conn.execute(sql, (
                exchange, symbol, tf, side, int(opened_ts_ms),
                float(payload["entry"]), float(payload["tp"]), float(payload["sl"]),
                float(payload.get("atr14")) if payload.get("atr14") is not None else None,
                float(payload.get("vol_mult")) if payload.get("vol_mult") is not None else None,
                float(payload.get("level")) if payload.get("level") is not None else None,
            )).fetchone()
            # 🚨 BUG FIX: Ambil ID dengan Dictionary Key, bukan Array Index!
            return r["id"] if r else None

    def close_trade(self, trade_id: int, closed_ts_ms: int, close_price: float, reason: str):
        sql = "UPDATE trades SET status='CLOSED', closed_ts_ms=%s, close_price=%s, close_reason=%s, closed_at=now() WHERE id=%s AND status='OPEN' RETURNING id;"
        with self.pool.connection() as conn:
            r = conn.execute(sql, (int(closed_ts_ms), float(close_price), reason, int(trade_id))).fetchone()
            return bool(r)

    def list_open_trades(self):
        sql = "SELECT * FROM trades WHERE status='OPEN' ORDER BY id ASC;"
        with self.pool.connection() as conn:
            rows = conn.execute(sql).fetchall()
            return [dict(r) for r in rows]

    # --- V1.7 SUMMARY METHODS ---
    def fetch_open_trades_count(self):
        sql = "SELECT COUNT(*) AS open_count FROM trades WHERE status='OPEN';"
        with self.pool.connection() as conn:
            row = conn.execute(sql).fetchone()
            return int(row["open_count"]) if row else 0

    def fetch_trade_stats_window(self, seconds: int):
        # Hitung PnL dinamis dari close_price dan entry (kolom pnl_pct tidak wajib ada)
        sql = """
        SELECT
          COUNT(*) FILTER (WHERE status='CLOSED') AS closed,
          COUNT(*) FILTER (WHERE status='CLOSED' AND (
              (side='LONG' AND close_price > entry) OR
              (side='SHORT' AND close_price < entry)
          )) AS wins,
          COUNT(*) FILTER (WHERE status='CLOSED' AND (
              (side='LONG' AND close_price <= entry) OR
              (side='SHORT' AND close_price >= entry)
          )) AS losses,
          COALESCE(AVG(
              CASE
                  WHEN side='LONG' THEN (close_price - entry) / entry * 100.0
                  WHEN side='SHORT' THEN (entry - close_price) / entry * 100.0
              END
          ) FILTER (WHERE status='CLOSED'), 0) AS avg_pnl,
          COALESCE(SUM(
              CASE
                  WHEN side='LONG' THEN (close_price - entry) / entry * 100.0
                  WHEN side='SHORT' THEN (entry - close_price) / entry * 100.0
              END
          ) FILTER (WHERE status='CLOSED'), 0) AS sum_pnl
        FROM trades
        WHERE closed_at >= now() - (%s || ' seconds')::interval;
        """
        with self.pool.connection() as conn:
            row = conn.execute(sql, (seconds,)).fetchone()
            return dict(row) if row else {}


    # --- V1.8 SETUP METHODS (partial index safe) ---
    def upsert_setup_pending(self, exchange, symbol, tf, side, created_ts_ms, expires_ts_ms, level, payload: dict):
        import json
        with self.pool.connection() as conn:
            # 1. Cek dulu apakah ada (Bukan Try-Except)
            check_sql = "SELECT id FROM trade_setups WHERE exchange=%s AND symbol=%s AND timeframe=%s AND status='PENDING';"
            row = conn.execute(check_sql, (exchange, symbol, tf)).fetchone()
            
            if row:
                # 2. Kalau ada, UPDATE
                update_sql = '''
                UPDATE trade_setups
                SET side=%s, created_ts_ms=%s, expires_ts_ms=%s, level=%s, payload=%s::jsonb, updated_at=now()
                WHERE id=%s RETURNING id;
                '''
                r = conn.execute(update_sql, (side, int(created_ts_ms), int(expires_ts_ms), float(level), json.dumps(payload), row["id"])).fetchone()
                return r["id"] if r else None
            else:
                # 3. Kalau belum ada, INSERT
                insert_sql = '''
                INSERT INTO trade_setups (exchange, symbol, timeframe, side, status, created_ts_ms, expires_ts_ms, level, payload)
                VALUES (%s,%s,%s,%s,'PENDING',%s,%s,%s,%s::jsonb) RETURNING id;
                '''
                r = conn.execute(insert_sql, (exchange, symbol, tf, side, int(created_ts_ms), int(expires_ts_ms), float(level), json.dumps(payload))).fetchone()
                return r["id"] if r else None

    def list_pending_setups(self):
        sql = "SELECT * FROM trade_setups WHERE status='PENDING' ORDER BY id ASC;"
        with self.pool.connection() as conn:
            rows = conn.execute(sql).fetchall()
            return [dict(r) for r in rows]

    def mark_setup_triggered(self, setup_id: int):
        sql = "UPDATE trade_setups SET status='TRIGGERED', updated_at=now() WHERE id=%s AND status='PENDING' RETURNING id;"
        with self.pool.connection() as conn:
            return bool(conn.execute(sql, (int(setup_id),)).fetchone())

    def mark_setup_expired(self, setup_id: int):
        sql = "UPDATE trade_setups SET status='EXPIRED', updated_at=now() WHERE id=%s AND status='PENDING' RETURNING id;"
        with self.pool.connection() as conn:
            return bool(conn.execute(sql, (int(setup_id),)).fetchone())
