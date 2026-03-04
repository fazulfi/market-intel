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
                pool = ConnectionPool(
                    conninfo=DB_DSN,
                    min_size=1,
                    max_size=10,
                    kwargs={"row_factory": dict_row}
                )
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
        INSERT INTO candles
        (exchange,symbol,timeframe,ts_ms,open,high,low,close,volume)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT DO NOTHING;
        """
        rows = [(exchange, symbol, tf, *c) for c in candles]
        with self.pool.connection() as conn:
            with conn.cursor() as cur:
                cur.executemany(sql, rows)

    def get_recent_candles(self, exchange, symbol, tf, limit):
        sql = """
        SELECT ts_ms,open,high,low,close,volume
        FROM candles
        WHERE exchange=%s AND symbol=%s AND timeframe=%s
        ORDER BY ts_ms DESC
        LIMIT %s;
        """
        with self.pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (exchange, symbol, tf, limit))
                rows = cur.fetchall()
        return list(reversed(rows))

    def insert_signal(self, exchange, symbol, tf, ts, stype, payload):
        sql = """
        INSERT INTO signals
        (exchange, symbol, timeframe, ts_ms, signal_type, payload)
        VALUES (%s,%s,%s,%s,%s,%s::jsonb)
        ON CONFLICT (exchange, symbol, timeframe, ts_ms, signal_type)
        DO NOTHING;
        """
        with self.pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (exchange, symbol, tf, ts, stype, json.dumps(payload)))

    def fetch_new_signals(self, last_id):
        sql = """
        SELECT * FROM signals
        WHERE id > %s ORDER BY id ASC LIMIT 100;
        """
        with self.pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (last_id,))
                return cur.fetchall()

    def mark_alert_sent(self, exchange, symbol, tf, ts, stype):
        sql = """
        INSERT INTO alerts
        (exchange,symbol,timeframe,ts_ms,signal_type)
        VALUES (%s,%s,%s,%s,%s)
        ON CONFLICT DO NOTHING;
        """
        with self.pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (exchange, symbol, tf, ts, stype))
                return cur.rowcount == 1
